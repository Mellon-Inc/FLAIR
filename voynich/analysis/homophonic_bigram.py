"""Bigram-extended homophonic decoder.

The 1-letter-per-word homophonic decoder (homophonic.py) hits a ceiling
(CE 4.23 bits/letter) even on synthetic Naibbe(Pliny), because Naibbe is a
**verbose** substitution: each Voynichese word can encode 1 OR 2 plaintext
letters. This script extends the decoder to learn that arity per word.

Each word in the top-N vocabulary is assigned EITHER:
  - A single letter (unigram word):  decode -> 1 letter
  - A pair of letters (bigram word): decode -> 2 letters

State: assign[i, 0] and assign[i, 1] in [0, 22]; flag arity[i] in {1, 2}.
Equivalent encoding: assign is shape (n_vocab, 2). When arity[i]=1 we use
only assign[i, 0].

Score: per-letter cross-entropy of the unrolled plaintext under a Latin
character bigram LM (no word boundaries).

Moves:
  M1: change assign[i, 0] for a unigram word to a different letter
  M2: change assign[i, 0] or assign[i, 1] for a bigram word
  M3: flip arity[i] from 1 to 2 (sample new letter for slot 1) or 2 to 1
      (drop slot 1)

For efficiency, we re-score from scratch on each move. Vectorised numpy
keeps each scoring at ~5 ms for 20K-letter streams.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva  # noqa: E402

ALPHABET = list("abcdefghilmnopqrstuvxyz")
ABC_INDEX = {c: i for i, c in enumerate(ALPHABET)}
N = len(ALPHABET)


# ------------------------- corpus -------------------------

EVA_LOWER = {"Sh": "sh", "cTh": "cth", "cKh": "ckh", "cPh": "cph", "cFh": "cfh"}

def to_naibbe_form(word: str) -> str:
    out = word
    for k, v in EVA_LOWER.items():
        out = out.replace(k, v)
    return out.replace("*", "").replace("!", "").replace("=", "")


SECTION_TO_DIALECT = {
    "Herbal": "A", "Pharmaceutical": "A",
    "Biological": "B", "Recipes": "B",
    "Cosmological": None, "Astronomical": None, "Unknown": None,
}


def load_dialect(d):
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    out = []
    for r in records:
        if SECTION_TO_DIALECT.get(r["section"]) != d:
            continue
        for w in r["words"]:
            if not w:
                continue
            nw = to_naibbe_form(w)
            if nw:
                out.append(nw)
    return out


def normalise(text):
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("w", "uu").replace("j", "i").replace("k", "c")
    return "".join(c for c in text if c in ABC_INDEX)


def train_bigram(path, smooth=0.5):
    text = path.read_text(encoding="utf-8", errors="ignore")
    letters = normalise(text)
    idxs = np.array([ABC_INDEX[c] for c in letters], dtype=np.int64)
    counts = np.zeros((N, N), dtype=np.float64)
    np.add.at(counts, (idxs[:-1], idxs[1:]), 1.0)
    row_sums = counts.sum(axis=1) + smooth * N
    log_p = np.log((counts + smooth) / row_sums[:, None])
    marg = np.bincount(idxs, minlength=N).astype(np.float64)
    log_marg = np.log((marg + smooth) / (marg.sum() + smooth * N))
    return log_p, log_marg


# ----------------- vocab -----------------

def build_vocab(words, n_top=500):
    counts = Counter(words)
    top = counts.most_common(n_top)
    word_to_idx = {w: i for i, (w, _) in enumerate(top)}
    n_covered = sum(c for _, c in top)
    return word_to_idx, [w for w, _ in top], n_covered, counts


def build_id_stream(words, word_to_idx):
    out = np.full(len(words), -1, dtype=np.int32)
    for i, w in enumerate(words):
        if w in word_to_idx:
            out[i] = word_to_idx[w]
    return out


# ----------------- scoring (bigram, vectorised) -----------------

def score_assignment(assign: np.ndarray, arity: np.ndarray,
                     id_stream: np.ndarray,
                     log_p: np.ndarray, log_marg: np.ndarray) -> tuple[float, int]:
    """Per-letter cross-entropy of the unrolled stream under the bigram LM.

    assign: shape (n_vocab, 2). arity: shape (n_vocab,) values in {1, 2}.
    OOV tokens (id == -1) are 'reset' positions.
    """
    valid_mask = id_stream >= 0
    valid_ids = id_stream[valid_mask]
    if valid_ids.size == 0:
        return float("inf"), 0
    arities = arity[valid_ids]
    # build the unrolled letter stream PLUS a parallel "is-fresh" mask
    # ("fresh" = first letter of a word that came right after a reset/OOV).
    valid_positions = np.where(valid_mask)[0]
    pos_diff = np.diff(valid_positions)
    adjacent = pos_diff == 1  # length n-1, True if no OOV between
    # is_fresh per word: True if it's the first word, or after a non-adjacent
    is_fresh_word = np.concatenate(([True], ~adjacent))

    # unroll letters and per-letter "fresh" flag
    out_letters = []
    out_fresh = []
    for k in range(valid_ids.size):
        wid = valid_ids[k]
        ar = arities[k]
        if ar == 1:
            out_letters.append(assign[wid, 0])
            out_fresh.append(is_fresh_word[k])
        else:  # arity 2
            out_letters.append(assign[wid, 0])
            out_letters.append(assign[wid, 1])
            out_fresh.append(is_fresh_word[k])
            out_fresh.append(False)  # second letter is bigram-conditioned on first
    letters = np.array(out_letters, dtype=np.int64)
    fresh = np.array(out_fresh, dtype=bool)
    n_letters = letters.size

    if n_letters == 0:
        return float("inf"), 0

    # score: each letter at position k contributes either log_marg[letters[k]]
    # if fresh[k] else log_p[letters[k-1], letters[k]]
    if n_letters == 1:
        total = float(log_marg[letters[0]])
    else:
        is_bigram = ~fresh.copy()
        is_bigram[0] = False
        bigram_idx = np.where(is_bigram)[0]
        bigram_total = log_p[letters[bigram_idx - 1], letters[bigram_idx]].sum()
        marg_idx = np.where(fresh)[0]
        marg_total = log_marg[letters[marg_idx]].sum()
        total = float(bigram_total + marg_total)
    return -total / n_letters / math.log(2), n_letters


def render_assignment(assign, arity, id_stream):
    parts = []
    for i in id_stream:
        if i == -1:
            parts.append("*")
        elif arity[i] == 1:
            parts.append(ALPHABET[assign[i, 0]])
        else:
            parts.append(ALPHABET[assign[i, 0]] + ALPHABET[assign[i, 1]])
    return "".join(parts)


# ----------------- SA -----------------

def sa_search(id_stream, log_p, log_marg, n_vocab,
              init_assign=None, init_arity=None,
              n_iters=400_000, T_start=0.4, T_end=0.005,
              seed=42, verbose=True):
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    if init_assign is None:
        assign = np_rng.randint(0, N, size=(n_vocab, 2), dtype=np.int64)
    else:
        assign = np.array(init_assign, dtype=np.int64).copy()
    if init_arity is None:
        arity = np_rng.randint(1, 3, size=n_vocab, dtype=np.int8)
    else:
        arity = np.array(init_arity, dtype=np.int8).copy()

    cur_ce, n_letters = score_assignment(assign, arity, id_stream, log_p, log_marg)
    best_ce = cur_ce
    best_assign = assign.copy()
    best_arity = arity.copy()
    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)
    last_print = time.time()
    t0 = time.time()
    accepts = 0
    rejects = 0
    for it in range(n_iters):
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        idx = rng.randrange(n_vocab)
        # move type: 70% letter change, 30% arity flip (with letter resample)
        if rng.random() < 0.7:
            slot = 0 if arity[idx] == 1 else rng.randint(0, 1)
            old_letter = assign[idx, slot]
            new_letter = rng.randrange(N - 1)
            if new_letter >= old_letter:
                new_letter += 1
            assign[idx, slot] = new_letter
            new_ce, _ = score_assignment(assign, arity, id_stream, log_p, log_marg)
            delta = new_ce - cur_ce
            if delta < 0 or rng.random() < math.exp(-delta / T):
                cur_ce = new_ce
                accepts += 1
                if cur_ce < best_ce:
                    best_ce = cur_ce
                    best_assign = assign.copy()
                    best_arity = arity.copy()
            else:
                assign[idx, slot] = old_letter
                rejects += 1
        else:
            old_arity = arity[idx]
            new_arity = 3 - old_arity  # 1 <-> 2
            old_assign1 = assign[idx, 1]
            arity[idx] = new_arity
            if new_arity == 2:
                # need a fresh second letter
                assign[idx, 1] = rng.randrange(N)
            new_ce, _ = score_assignment(assign, arity, id_stream, log_p, log_marg)
            delta = new_ce - cur_ce
            if delta < 0 or rng.random() < math.exp(-delta / T):
                cur_ce = new_ce
                accepts += 1
                if cur_ce < best_ce:
                    best_ce = cur_ce
                    best_assign = assign.copy()
                    best_arity = arity.copy()
            else:
                arity[idx] = old_arity
                assign[idx, 1] = old_assign1
                rejects += 1

        if verbose and time.time() - last_print > 4:
            rate = (it + 1) / (time.time() - t0)
            n_bigram = int((arity == 2).sum())
            print(f"  iter {it:>7}  T={T:.4f}  cur={cur_ce:.4f}  best={best_ce:.4f}  "
                  f"bigrams={n_bigram}/{n_vocab}  ({rate:.0f} it/s)", flush=True)
            last_print = time.time()
    if verbose:
        print(f"  done in {time.time()-t0:.1f}s. best={best_ce:.4f}", flush=True)
    return best_assign, best_arity, best_ce, n_letters


# ----------------- main -----------------

def main():
    print("=== Loading bigram LM ===", flush=True)
    lat_log_p, lat_log_marg = train_bigram(DATA / "comparison" / "latin_pliny.txt")
    ita_log_p, ita_log_marg = train_bigram(DATA / "comparison" / "italian_dc.txt")

    # ---- SANITY: synthetic Naibbe(Pliny) with bigram extension ----
    print("\n=== SANITY: bigram homophonic on synthetic Naibbe(Pliny) ===", flush=True)
    pliny = (DATA / "naibbe" / "naibbe_pliny_book16.txt").read_text(encoding="utf-8").split()
    word_to_idx, top_words, n_cov, counts = build_vocab(pliny, n_top=500)
    print(f"  top-500 covers {n_cov}/{len(pliny)} ({100*n_cov/len(pliny):.1f}%)",
          flush=True)
    id_stream = build_id_stream(pliny, word_to_idx)
    a, ar, ce, _ = sa_search(id_stream, lat_log_p, lat_log_marg, n_vocab=500,
                              n_iters=300_000, seed=42, verbose=True)
    sample = render_assignment(a, ar, id_stream[:200])
    print(f"  Recovered CE = {ce:.4f}  (target: ~3.59 if Naibbe-perfect)", flush=True)
    print(f"  Sample: {sample[:300]}", flush=True)
    sanity_ce = ce
    sanity_sample = sample[:300]
    # Inspect: how many bigram-arity?
    n_bi = int((ar == 2).sum())
    print(f"  {n_bi}/500 words assigned arity 2 (bigram chunk)", flush=True)

    # ---- REAL B-system ----
    print("\n=== REAL B-system bigram homophonic decoder ===", flush=True)
    B = load_dialect("B")
    word_to_idx_B, top_words_B, n_cov_B, counts_B = build_vocab(B, n_top=500)
    id_stream_B = build_id_stream(B, word_to_idx_B)
    print(f"  {len(B)} tokens, top-500 covers {100*n_cov_B/len(B):.1f}%", flush=True)

    best_a = best_ar = None
    best_ce = float("inf")
    for restart in range(3):
        seed = 3000 + restart
        print(f"\n  Restart {restart} (seed {seed}):", flush=True)
        a, ar, c, _ = sa_search(id_stream_B, lat_log_p, lat_log_marg, n_vocab=500,
                                 n_iters=300_000, seed=seed,
                                 verbose=(restart == 0))
        print(f"    best CE = {c:.4f}", flush=True)
        if c < best_ce:
            best_ce = c
            best_a = a
            best_ar = ar

    print(f"\n  >>> B best CE under Latin = {best_ce:.4f}", flush=True)
    decoded_B = render_assignment(best_a, best_ar, id_stream_B)
    print(f"  First 800 chars: {decoded_B[:800]}", flush=True)

    # cross-entropy under Italian
    ce_ita, _ = score_assignment(best_a, best_ar, id_stream_B, ita_log_p, ita_log_marg)
    print(f"  CE under Italian = {ce_ita:.4f}", flush=True)

    # show top word -> letters
    print(f"\n  Top-30 B word assignments:", flush=True)
    for i, w in enumerate(top_words_B[:30]):
        ar_w = best_ar[i]
        if ar_w == 1:
            letters_str = ALPHABET[best_a[i, 0]]
        else:
            letters_str = ALPHABET[best_a[i, 0]] + ALPHABET[best_a[i, 1]]
        print(f"    {w:<14}  count={counts_B[w]:>4}  -> {letters_str}", flush=True)

    out = {
        "alphabet": ALPHABET,
        "n_top_vocab": 500,
        "sanity_synthetic_pliny_ce": sanity_ce,
        "sanity_sample_first_300": sanity_sample,
        "B_best_ce_latin": best_ce,
        "B_best_ce_italian": ce_ita,
        "B_decoded_first_1000": decoded_B[:1000],
        "B_top_30_assignments": [
            {"word": w, "count": counts_B[w],
             "letters": (ALPHABET[best_a[i, 0]] if best_ar[i] == 1
                         else ALPHABET[best_a[i, 0]] + ALPHABET[best_a[i, 1]]),
             "arity": int(best_ar[i])}
            for i, w in enumerate(top_words_B[:30])
        ],
    }
    (ROOT / "homophonic_bigram_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "homophonic_bigram_decoded_B.txt").write_text(
        decoded_B, encoding="utf-8")
    print(f"\nWrote {ROOT/'homophonic_bigram_results.json'}", flush=True)


if __name__ == "__main__":
    main()
