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

def build_unroll(id_stream: np.ndarray, arity: np.ndarray):
    """Pre-compute index arrays for vectorised scoring.

    Returns (word_idx, slot_idx, fresh):
      word_idx[k]  = vocab index whose token contributed letter k
      slot_idx[k]  = 0 or 1 (which slot of that word)
      fresh[k]     = True iff letter k is the FIRST letter of a Voynichese
                     word that itself follows a reset (OOV / start)
    """
    valid_mask = id_stream >= 0
    valid_ids = id_stream[valid_mask]
    if valid_ids.size == 0:
        return (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64),
                np.zeros(0, dtype=bool))
    arities = arity[valid_ids].astype(np.int64)
    total = int(arities.sum())

    word_idx = np.repeat(valid_ids.astype(np.int64), arities)
    # slot_idx: for arities [1, 2, 1, 2] -> [0, 0, 1, 0, 0, 1]
    # arange of total minus cumulative offset
    cum_offsets = np.concatenate(([0], np.cumsum(arities)[:-1]))
    slot_idx = np.arange(total, dtype=np.int64) - np.repeat(cum_offsets, arities)

    # is_fresh per Voynichese word
    valid_positions = np.where(valid_mask)[0]
    if valid_positions.size > 1:
        pos_diff = np.diff(valid_positions)
        is_fresh_word = np.concatenate(([True], pos_diff != 1))
    else:
        is_fresh_word = np.array([True])

    # offset of each word's first letter in the output
    offsets = cum_offsets  # length n_valid
    fresh = np.zeros(total, dtype=bool)
    fresh[offsets] = is_fresh_word
    return word_idx, slot_idx, fresh


def score_with_unroll(assign: np.ndarray,
                      word_idx: np.ndarray, slot_idx: np.ndarray,
                      fresh: np.ndarray,
                      log_p: np.ndarray, log_marg: np.ndarray) -> tuple[float, int]:
    """Vectorised per-letter cross-entropy."""
    n = word_idx.size
    if n == 0:
        return float("inf"), 0
    letters = assign[word_idx, slot_idx]
    fresh_letters = letters[fresh]
    fresh_total = float(log_marg[fresh_letters].sum())
    nonfresh_idx = np.where(~fresh)[0]
    if nonfresh_idx.size > 0:
        nonfresh_total = float(
            log_p[letters[nonfresh_idx - 1], letters[nonfresh_idx]].sum()
        )
    else:
        nonfresh_total = 0.0
    total = fresh_total + nonfresh_total
    return -total / n / math.log(2), n


def score_assignment(assign, arity, id_stream, log_p, log_marg):
    """Compatibility wrapper: rebuild unroll structure each call.

    Use score_with_unroll inside hot SA loop; this is for one-off calls.
    """
    word_idx, slot_idx, fresh = build_unroll(id_stream, arity)
    return score_with_unroll(assign, word_idx, slot_idx, fresh, log_p, log_marg)


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

    # Build unroll structure ONCE; rebuild only on arity flips.
    word_idx, slot_idx, fresh = build_unroll(id_stream, arity)
    cur_ce, n_letters = score_with_unroll(assign, word_idx, slot_idx, fresh,
                                           log_p, log_marg)
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
        # move type: 80% letter change (no rebuild), 20% arity flip (rebuild)
        if rng.random() < 0.8:
            slot = 0 if arity[idx] == 1 else rng.randint(0, 1)
            old_letter = assign[idx, slot]
            new_letter = rng.randrange(N - 1)
            if new_letter >= old_letter:
                new_letter += 1
            assign[idx, slot] = new_letter
            new_ce, _ = score_with_unroll(assign, word_idx, slot_idx, fresh,
                                           log_p, log_marg)
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
            new_arity = 3 - old_arity
            old_assign1 = assign[idx, 1]
            arity[idx] = new_arity
            if new_arity == 2:
                assign[idx, 1] = rng.randrange(N)
            new_word_idx, new_slot_idx, new_fresh = build_unroll(id_stream, arity)
            new_ce, _ = score_with_unroll(assign, new_word_idx, new_slot_idx,
                                           new_fresh, log_p, log_marg)
            delta = new_ce - cur_ce
            if delta < 0 or rng.random() < math.exp(-delta / T):
                cur_ce = new_ce
                accepts += 1
                word_idx, slot_idx, fresh = new_word_idx, new_slot_idx, new_fresh
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
