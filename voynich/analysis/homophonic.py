"""Glyph-free homophonic substitution decoder.

Phase 8 showed that a 23-letter alphabet permutation of Greshko's Naibbe
codebook cannot crack Voynichese (gap 0.78 bits/letter to the Latin floor).
The reason is presumably that Greshko's specific glyph strings are not the
real cipher's glyph strings — only the structure (verbose substitution onto
a slot grammar) is shared.

This script abandons Greshko's tables entirely. We treat each frequent
Voynichese word type as an opaque ciphertext "homophone" and learn its
plaintext-letter assignment directly from a Latin bigram language model.

Concretely:
  - Take the top-N most frequent Voynichese word types in dialect B.
  - Assign each one a plaintext letter from the 23-letter alphabet.
  - Tokens of words outside top-N are treated as "*" (skipped in scoring).
  - Score: per-letter cross-entropy of the (word -> letter)-mapped stream
    under a Latin character bigram LM.
  - Move: change ONE word's letter assignment (23 options).
  - Simulated annealing over assignments.

This is equivalent to a homophonic-substitution-cipher attack with N
ciphertext symbols mapping onto 23 plaintext letters. Naibbe-style ciphers
have ~150 ciphertext symbols per plaintext letter, well within the
recoverable regime for classical homophonic cryptanalysis.

Sanity check: run on synthetic Naibbe(Pliny). If the decoder cannot
recover readable Latin from a known Naibbe ciphertext, the method is
inadequate. If it can, the method works and we apply it to real Voynichese.

If the recovered Voynichese B plaintext looks like Latin words, we win.
If not, we have a quantitative bound on how Latin-shaped Voynichese is
under any homophonic substitution.
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

ALPHABET = list("abcdefghilmnopqrstuvxyz")  # 23 letters (Naibbe alphabet)
ABC_INDEX = {c: i for i, c in enumerate(ALPHABET)}
N_LETTERS = len(ALPHABET)


# ------------------------- corpus loading -------------------------

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


def load_dialect(d: str) -> list[str]:
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


# ------------------------- bigram LM -------------------------

def normalise(text: str) -> str:
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("w", "uu").replace("j", "i").replace("k", "c")
    return "".join(c for c in text if c in ABC_INDEX)


def train_bigram(corpus_path: Path, smooth: float = 0.5):
    text = corpus_path.read_text(encoding="utf-8", errors="ignore")
    letters = normalise(text)
    idxs = np.array([ABC_INDEX[c] for c in letters], dtype=np.int64)
    counts = np.zeros((N_LETTERS, N_LETTERS), dtype=np.float64)
    np.add.at(counts, (idxs[:-1], idxs[1:]), 1.0)
    row_sums = counts.sum(axis=1) + smooth * N_LETTERS
    log_p = np.log((counts + smooth) / row_sums[:, None])
    marg = np.bincount(idxs, minlength=N_LETTERS).astype(np.float64)
    log_marg = np.log((marg + smooth) / (marg.sum() + smooth * N_LETTERS))
    return log_p, log_marg


# ------------------- vocabulary indexing -------------------

def build_vocabulary(words: list[str], n_top: int = 500):
    """Return (word_to_idx, top_words, n_covered) where word_to_idx maps each
    of the top-N word types to an index in 0..N-1, and n_covered is the
    number of tokens whose word type is in the top-N."""
    counts = Counter(words)
    top = counts.most_common(n_top)
    word_to_idx = {w: i for i, (w, _) in enumerate(top)}
    n_covered = sum(c for _, c in top)
    return word_to_idx, [w for w, _ in top], n_covered, counts


def words_to_id_stream(words: list[str], word_to_idx: dict[str, int]) -> np.ndarray:
    """Return int32 array of word-type indices, with -1 for words outside
    the top-N vocabulary (these will be treated as 'reset' positions in
    scoring)."""
    n = len(words)
    out = np.full(n, -1, dtype=np.int32)
    for i, w in enumerate(words):
        if w in word_to_idx:
            out[i] = word_to_idx[w]
    return out


# ------------------- scoring -------------------

def score_assignment(assign: np.ndarray, id_stream: np.ndarray,
                     log_p: np.ndarray, log_marg: np.ndarray) -> tuple[float, int]:
    """Per-letter cross-entropy.

    `assign[i]` = the plaintext letter index assigned to vocab word i.
    `id_stream` is the per-token vocab index (-1 if out-of-vocab).

    For consecutive tokens (id_a, id_b) where both >= 0, we score
    log_p[assign[id_a], assign[id_b]]. For tokens where id is -1, we
    "reset" — the next valid token is scored with log_marg.
    """
    valid_mask = id_stream >= 0
    valid_ids = id_stream[valid_mask]
    if valid_ids.size == 0:
        return float("inf"), 0
    mapped = assign[valid_ids]
    n = mapped.size

    # for bigram scoring we need to know which valid positions are adjacent
    # in the original (non-reset) stream. Two valid positions are "adjacent"
    # if there is no -1 between them.
    valid_positions = np.where(valid_mask)[0]
    # for each pair (k-1, k) of valid positions in the valid_ids array,
    # they are adjacent iff valid_positions[k] - valid_positions[k-1] == 1
    pos_diff = np.diff(valid_positions)
    adjacent = pos_diff == 1  # length n-1

    # bigram score where adjacent
    bigram_idx = np.where(adjacent)[0]
    if bigram_idx.size > 0:
        a = mapped[bigram_idx]
        b = mapped[bigram_idx + 1]
        bigram_total = log_p[a, b].sum()
    else:
        bigram_total = 0.0

    # marginal score for "fresh" positions: 0 (start) and any after a reset
    fresh_mask = np.concatenate(([True], ~adjacent))  # length n
    marg_total = log_marg[mapped[fresh_mask]].sum()

    total = bigram_total + marg_total
    return -float(total) / n / math.log(2), n


def apply_assignment(assign: np.ndarray, id_stream: np.ndarray,
                     vocab_words: list[str]) -> str:
    """Render the decoded plaintext as a string (with '*' for OOV)."""
    out = []
    for i in id_stream:
        if i == -1:
            out.append("*")
        else:
            out.append(ALPHABET[assign[i]])
    return "".join(out)


# ------------------- MCMC -------------------

def sa_search(id_stream, log_p, log_marg, n_vocab,
              init_assign=None, n_iters=300_000,
              T_start=0.4, T_end=0.005, seed=42, verbose=True):
    rng = random.Random(seed)
    assign = (np.array(init_assign, dtype=np.int64)
              if init_assign is not None else
              np.random.RandomState(seed).randint(0, N_LETTERS, size=n_vocab))
    cur_ce, n_letters = score_assignment(assign, id_stream, log_p, log_marg)
    best_ce = cur_ce
    best_assign = assign.copy()
    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)
    accepts = 0
    rejects = 0
    last_print = time.time()
    t0 = time.time()
    for it in range(n_iters):
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        # propose: pick a vocab word, change its letter to a random other letter
        idx = rng.randrange(n_vocab)
        old_letter = assign[idx]
        new_letter = rng.randrange(N_LETTERS - 1)
        if new_letter >= old_letter:
            new_letter += 1
        assign[idx] = new_letter
        new_ce, _ = score_assignment(assign, id_stream, log_p, log_marg)
        delta = new_ce - cur_ce
        if delta < 0 or rng.random() < math.exp(-delta / T):
            cur_ce = new_ce
            accepts += 1
            if cur_ce < best_ce:
                best_ce = cur_ce
                best_assign = assign.copy()
        else:
            assign[idx] = old_letter
            rejects += 1
        if verbose and time.time() - last_print > 4:
            rate = (it + 1) / (time.time() - t0)
            print(f"  iter {it:>7}  T={T:.4f}  cur={cur_ce:.4f}  best={best_ce:.4f}  "
                  f"accepts={accepts} rejects={rejects}  ({rate:.0f} it/s)",
                  flush=True)
            last_print = time.time()
    if verbose:
        print(f"  done in {time.time()-t0:.1f}s. best_ce={best_ce:.4f}", flush=True)
    return best_assign, best_ce, n_letters


# ------------------- initialisation heuristics -------------------

def init_by_word_frequency(top_words: list[str], counts: Counter) -> np.ndarray:
    """Heuristic: assign letters in proportion to Latin letter frequencies,
    so the most frequent Voynichese words get assigned to the most frequent
    Latin letters (e, i, t, a, ...). This is the classic homophonic-cipher
    starting point.
    """
    LATIN_FREQ_ORDER = list("eitausrnomcdplgfbhvqxyz")
    LATIN_FREQ_ORDER = [c for c in LATIN_FREQ_ORDER if c in ABC_INDEX]
    assign = np.zeros(len(top_words), dtype=np.int64)
    for i, w in enumerate(top_words):
        # cycle through Latin letters in frequency-rank order
        # most frequent words get the most frequent letters
        assign[i] = ABC_INDEX[LATIN_FREQ_ORDER[i % len(LATIN_FREQ_ORDER)]]
    return assign


# ------------------- main -------------------

def main():
    print("=== Loading bigram LM (Latin / Pliny) ===", flush=True)
    lat_log_p, lat_log_marg = train_bigram(DATA / "comparison" / "latin_pliny.txt")
    ita_log_p, ita_log_marg = train_bigram(DATA / "comparison" / "italian_dc.txt")
    fin_log_p, fin_log_marg = train_bigram(DATA / "comparison" / "finnish_bible.txt")

    # ----- SANITY: synthetic Naibbe(Pliny), top-500 word types -----
    print("\n=== SANITY: homophonic decoder on synthetic Naibbe(Pliny) ===", flush=True)
    pliny_naibbe = (DATA / "naibbe" / "naibbe_pliny_book16.txt") \
        .read_text(encoding="utf-8").split()
    print(f"  {len(pliny_naibbe)} tokens, {len(set(pliny_naibbe))} types", flush=True)
    word_to_idx, top_words, n_cov, counts = build_vocabulary(pliny_naibbe, n_top=500)
    print(f"  top-500 words cover {n_cov}/{len(pliny_naibbe)} tokens "
          f"({100*n_cov/len(pliny_naibbe):.1f}%)", flush=True)
    id_stream = words_to_id_stream(pliny_naibbe, word_to_idx)

    init = init_by_word_frequency(top_words, counts)
    ce_init, _ = score_assignment(init, id_stream, lat_log_p, lat_log_marg)
    print(f"  Latin-frequency-init CE = {ce_init:.4f}", flush=True)

    print("  Running SA (200K iters)...", flush=True)
    best_assign, best_ce, n_letters = sa_search(
        id_stream, lat_log_p, lat_log_marg, n_vocab=500,
        init_assign=init, n_iters=200_000, seed=42, verbose=True)
    sample = apply_assignment(best_assign, id_stream[:200], top_words)
    print(f"  Recovered CE = {best_ce:.4f} (target: ~3.5 if works perfectly)", flush=True)
    print(f"  Sample plaintext: {sample[:300]}", flush=True)
    sanity_ce = best_ce
    sanity_sample = sample

    # ----- REAL B-system, top-500 word types -----
    print("\n=== REAL B-system homophonic decoder ===", flush=True)
    B = load_dialect("B")
    print(f"  {len(B)} tokens, {len(set(B))} types", flush=True)
    word_to_idx_B, top_words_B, n_cov_B, counts_B = build_vocabulary(B, n_top=500)
    print(f"  top-500 covers {n_cov_B}/{len(B)} tokens ({100*n_cov_B/len(B):.1f}%)",
          flush=True)
    id_stream_B = words_to_id_stream(B, word_to_idx_B)

    best_b_assign = None
    best_b_ce = float("inf")
    for restart in range(3):
        if restart == 0:
            init_b = init_by_word_frequency(top_words_B, counts_B)
            label = "freq-init"
        else:
            rng = np.random.RandomState(1000 + restart)
            init_b = rng.randint(0, N_LETTERS, size=500)
            label = f"random{restart}"
        ce_i, _ = score_assignment(init_b, id_stream_B, lat_log_p, lat_log_marg)
        print(f"\n  Restart {restart} ({label}): init CE = {ce_i:.4f}", flush=True)
        a, c, _ = sa_search(id_stream_B, lat_log_p, lat_log_marg, n_vocab=500,
                            init_assign=init_b, n_iters=300_000,
                            seed=2000 + restart, verbose=(restart == 0))
        print(f"    best CE = {c:.4f}", flush=True)
        if c < best_b_ce:
            best_b_ce = c
            best_b_assign = a

    print(f"\n  >>> B best CE under Latin = {best_b_ce:.4f}", flush=True)
    decoded_B = apply_assignment(best_b_assign, id_stream_B, top_words_B)
    print(f"  First 600 chars: {decoded_B[:600]}", flush=True)

    # cross-evaluate
    ce_b_lat, _ = score_assignment(best_b_assign, id_stream_B, lat_log_p, lat_log_marg)
    ce_b_ita, _ = score_assignment(best_b_assign, id_stream_B, ita_log_p, ita_log_marg)
    ce_b_fin, _ = score_assignment(best_b_assign, id_stream_B, fin_log_p, fin_log_marg)
    print(f"  CE under Latin   = {ce_b_lat:.4f}", flush=True)
    print(f"  CE under Italian = {ce_b_ita:.4f}", flush=True)
    print(f"  CE under Finnish = {ce_b_fin:.4f}", flush=True)

    # show top-30 word -> letter assignments
    print(f"\n  Top-30 most frequent B words and their assigned letters:", flush=True)
    for i, w in enumerate(top_words_B[:30]):
        L = ALPHABET[best_b_assign[i]]
        print(f"    {w:<14}  count={counts_B[w]:>4}  -> {L}", flush=True)

    # ----- save -----
    out = {
        "alphabet": ALPHABET,
        "n_top_vocab": 500,
        "sanity": {
            "ce_init": ce_init,
            "ce_recovered": sanity_ce,
            "sample": sanity_sample[:600],
        },
        "B_best_ce_latin": ce_b_lat,
        "B_best_ce_italian": ce_b_ita,
        "B_best_ce_finnish": ce_b_fin,
        "B_decoded_first_1000": decoded_B[:1000],
        "B_top_30_assignments": [
            {"word": w, "count": counts_B[w],
             "letter": ALPHABET[best_b_assign[i]]}
            for i, w in enumerate(top_words_B[:30])
        ],
    }
    (ROOT / "homophonic_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "homophonic_decoded_B.txt").write_text(decoded_B, encoding="utf-8")
    print(f"\nWrote {ROOT/'homophonic_results.json'}", flush=True)


if __name__ == "__main__":
    main()
