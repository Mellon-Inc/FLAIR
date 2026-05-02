"""EM-style learning of multi-candidate Voynichese cipher table.

Phase 9 forced each Voynichese word type to ONE plaintext letter sequence,
hitting CE 4.14 bits/letter on real B (Latin true is 3.59).
Phase 10 used Greshko's specific candidates with Viterbi but stalled at
4.23 because Greshko's exact glyph strings don't match real Voynichese.

This script combines the two: each word type w has up to K plaintext
letter-sequence candidates, all LEARNED FROM DATA via simulated annealing,
and at each token occurrence, Viterbi picks the best candidate using
Latin bigram LM context. This is the homophonic-substitution-cipher attack
in its full form (Naibbe-style verbose, with multiple homophones per
plaintext letter and per cipher word).

Sanity expectation:
  - Synthetic Naibbe(Pliny) from random init: should hit ~Latin true
    (3.59) since Viterbi can resolve table-choice ambiguity if the
    candidates approximate the real table contents.
  - Real B-system: see how close to Latin true we can get.

This is the most ambitious / longest-running experiment in the project.
Search space is enormous (each of K=4 candidates per word can be 23 +
23*23 = 552 letter sequences). We use SA from the Phase 9 single-cand
solution as init, plus a few random restarts.
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
K_DEFAULT = 4  # candidates per word


# ----------------- corpus -----------------

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

def build_vocab(words, n_top=400):
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


# ----------------- multi-candidate model -----------------
# Representation:
#   cands: int8 array shape (n_vocab, K, 2). cands[v, k, 0] = first letter,
#                                           cands[v, k, 1] = second letter or -1 if arity=1
#   For arity-1 candidate: cands[v, k] = (l, -1)
#   For arity-2 candidate: cands[v, k] = (l1, l2) with both in 0..22

def init_candidates(n_vocab: int, K: int, single_assign=None, single_arity=None,
                    seed=0):
    """Initialize candidate matrix.

    If single_assign and single_arity are provided (from Phase 9), the first
    candidate of each word is set to that solution; remaining K-1 candidates
    are random.
    """
    rng = np.random.RandomState(seed)
    cands = np.full((n_vocab, K, 2), -1, dtype=np.int8)
    # Random init for all
    for v in range(n_vocab):
        for k in range(K):
            l1 = rng.randint(0, N)
            ar = rng.randint(1, 3)  # 1 or 2
            cands[v, k, 0] = l1
            if ar == 2:
                cands[v, k, 1] = rng.randint(0, N)
    # Override first candidate with Phase 9 solution if provided
    if single_assign is not None and single_arity is not None:
        for v in range(n_vocab):
            cands[v, 0, 0] = single_assign[v, 0]
            if single_arity[v] == 2:
                cands[v, 0, 1] = single_assign[v, 1]
            else:
                cands[v, 0, 1] = -1
    return cands


def viterbi_score(cands: np.ndarray, id_stream: np.ndarray,
                   log_p: np.ndarray, log_marg: np.ndarray):
    """Per-letter cross-entropy of the best path through multi-candidates.

    Returns (ce, n_letters, decoded_letters_array, candidate_choices_array).
    """
    NEG_INF = -1e18
    n_vocab, K, _ = cands.shape
    n_tokens = id_stream.size

    # Precompute: for each (v, k), letters tuple and arity, and internal score
    # internal[v, k] = log_p[l1, l2] if arity 2 else 0
    arity = (cands[:, :, 1] >= 0).astype(np.int8) + 1  # shape (V, K)
    # For internal score we need log_p[l1, l2] for arity-2 candidates
    l1 = cands[:, :, 0].astype(np.int64)
    l2 = cands[:, :, 1].astype(np.int64)
    # safe l2: where -1, use 0 (won't be used because arity=1)
    l2_safe = np.where(l2 < 0, 0, l2)
    internal = np.where(arity == 2,
                        log_p[l1, l2_safe],
                        0.0)
    # exit letter (last letter of candidate): for arity 1, it's l1; for 2, l2
    exit_letter = np.where(arity == 2, l2_safe, l1)
    first_letter = l1  # always l1

    # Viterbi DP. State at any point = last decoded letter (or BOS).
    # dp[L] for L in 0..N-1 = best log-likelihood ending in letter L
    # plus dp_bos = best log-likelihood with no letter yet emitted
    # (only used at BOS).
    dp = np.full(N + 1, NEG_INF, dtype=np.float64)
    dp[N] = 0.0  # BOS slot
    # backpointers
    bp_prev = np.full((n_tokens, N), -1, dtype=np.int32)  # prev letter (or N=BOS)
    bp_cand = np.full((n_tokens, N), -1, dtype=np.int8)   # candidate index
    bp_kind = np.zeros(n_tokens, dtype=np.int8)  # 0=OK, 1=OOV (skip)

    for t_idx in range(n_tokens):
        v = id_stream[t_idx]
        if v < 0:
            # OOV: dp unchanged
            bp_kind[t_idx] = 1
            continue

        # candidates for this word: arity[v], internal[v], first_letter[v],
        # exit_letter[v], all shape (K,)
        ar_v = arity[v]
        f_v = first_letter[v]
        e_v = exit_letter[v]
        in_v = internal[v]

        # For each candidate k:
        #   For each prev state L (incl BOS=N):
        #     if L < N: trans = log_p[L, f_v[k]]
        #     else (BOS): trans = log_marg[f_v[k]]
        #     score = dp[L] + trans + in_v[k]
        #     end_letter = e_v[k]
        # Take the best for each end letter and update new_dp.
        new_dp = np.full(N, NEG_INF)
        # For each candidate: compute scores from all previous states
        # vectorise over previous letter (23 + 1 BOS slot)
        for k in range(K):
            if f_v[k] < 0:  # invalid
                continue
            trans_from_L = dp[:N] + log_p[:N, f_v[k]]  # shape (N,)
            trans_from_BOS = dp[N] + log_marg[f_v[k]]
            # combine: max over previous state
            best_from_L_idx = int(np.argmax(trans_from_L))
            best_from_L = trans_from_L[best_from_L_idx]
            if best_from_L > trans_from_BOS:
                best_score = best_from_L + in_v[k]
                best_prev = best_from_L_idx
            else:
                best_score = trans_from_BOS + in_v[k]
                best_prev = N
            # update new_dp at exit letter
            ee = e_v[k]
            if best_score > new_dp[ee]:
                new_dp[ee] = best_score
                bp_prev[t_idx, ee] = best_prev
                bp_cand[t_idx, ee] = k
        dp = np.concatenate([new_dp, [NEG_INF]])

    # Backtrack
    final_ll = dp[:N].max()
    if final_ll <= NEG_INF / 2:
        return float("inf"), 0, "", []

    cur = int(np.argmax(dp[:N]))
    out_letters = []
    cand_choices = []
    for t in range(n_tokens - 1, -1, -1):
        if bp_kind[t] == 1:
            cand_choices.append(-1)
            continue
        if cur < 0 or cur >= N:
            cand_choices.append(-1)
            continue
        prev = bp_prev[t, cur]
        k = bp_cand[t, cur]
        if k < 0:
            cand_choices.append(-1)
            continue
        cand_choices.append(int(k))
        # decode this token's letters
        v = id_stream[t]
        if v >= 0:
            ar = int(arity[v, k])
            if ar == 2:
                out_letters.append(int(cands[v, k, 1]))
                out_letters.append(int(cands[v, k, 0]))
            else:
                out_letters.append(int(cands[v, k, 0]))
        cur = prev if prev != N else -1
    out_letters.reverse()
    cand_choices.reverse()
    n_letters = len(out_letters)
    if n_letters == 0:
        return float("inf"), 0, "", []
    ce = -float(final_ll) / n_letters / math.log(2)
    decoded = "".join(ALPHABET[l] for l in out_letters)
    return ce, n_letters, decoded, cand_choices


# ----------------- SA -----------------

def sa_search(id_stream, log_p, log_marg, n_vocab, K=K_DEFAULT,
              init_cands=None, n_iters=2000, T_start=0.3, T_end=0.005,
              seed=42, verbose=True):
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    if init_cands is None:
        cands = init_candidates(n_vocab, K, seed=seed)
    else:
        cands = init_cands.copy()

    cur_ce, n_letters, _, _ = viterbi_score(cands, id_stream, log_p, log_marg)
    best_ce = cur_ce
    best_cands = cands.copy()
    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)
    accepts = 0
    rejects = 0
    last_print = time.time()
    t0 = time.time()
    for it in range(n_iters):
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        # Move types:
        #   60%: change a letter in a candidate
        #   25%: flip arity of a candidate (with letter resample)
        #   15%: replace a candidate entirely
        v = rng.randrange(n_vocab)
        k = rng.randrange(K)
        move = rng.random()
        old_l0, old_l1 = int(cands[v, k, 0]), int(cands[v, k, 1])
        if move < 0.60:
            # change one letter
            slot = 0 if old_l1 < 0 else rng.randint(0, 1)
            new_letter = rng.randrange(N - 1)
            old = int(cands[v, k, slot])
            if new_letter >= old:
                new_letter += 1
            cands[v, k, slot] = new_letter
        elif move < 0.85:
            # flip arity
            if old_l1 < 0:  # was arity 1, make 2
                cands[v, k, 1] = rng.randrange(N)
            else:  # was arity 2, make 1
                cands[v, k, 1] = -1
        else:
            # replace candidate
            cands[v, k, 0] = rng.randrange(N)
            cands[v, k, 1] = rng.randrange(N) if rng.random() < 0.5 else -1

        new_ce, _, _, _ = viterbi_score(cands, id_stream, log_p, log_marg)
        delta = new_ce - cur_ce
        if delta < 0 or rng.random() < math.exp(-delta / T):
            cur_ce = new_ce
            accepts += 1
            if cur_ce < best_ce:
                best_ce = cur_ce
                best_cands = cands.copy()
        else:
            cands[v, k, 0] = old_l0
            cands[v, k, 1] = old_l1
            rejects += 1
        if verbose and time.time() - last_print > 5:
            rate = (it + 1) / (time.time() - t0)
            print(f"  it {it+1:>5}/{n_iters} T={T:.4f} cur={cur_ce:.4f} "
                  f"best={best_ce:.4f} ({rate:.1f} it/s)", flush=True)
            last_print = time.time()
    if verbose:
        print(f"  done in {time.time()-t0:.1f}s. best={best_ce:.4f} "
              f"(accept rate {accepts/max(1, accepts+rejects):.2%})", flush=True)
    return best_cands, best_ce


# ----------------- main -----------------

def main():
    print("=== Loading bigram LM ===", flush=True)
    log_p, log_marg = train_bigram(DATA / "comparison" / "latin_pliny.txt")
    log_p_ita, log_marg_ita = train_bigram(DATA / "comparison" / "italian_dc.txt")

    n_top = 300
    K = 3
    n_iters = 2500  # full Viterbi each iter, ~2.8 it/s -> ~15 min per run

    # ----- SANITY: synthetic Naibbe(Pliny) -----
    print(f"\n=== SANITY: multi-cand SA on synthetic Naibbe(Pliny), K={K} ===", flush=True)
    pliny = (DATA / "naibbe" / "naibbe_pliny_book16.txt") \
        .read_text(encoding="utf-8").split()
    word_to_idx, top_words, n_cov, counts = build_vocab(pliny, n_top=n_top)
    print(f"  top-{n_top} covers {n_cov}/{len(pliny)} ({100*n_cov/len(pliny):.1f}%)",
          flush=True)
    id_stream = build_id_stream(pliny, word_to_idx)
    cands_init = init_candidates(n_top, K, seed=42)
    init_ce, _, _, _ = viterbi_score(cands_init, id_stream, log_p, log_marg)
    print(f"  initial random CE = {init_ce:.4f}", flush=True)
    best_cands, best_ce = sa_search(id_stream, log_p, log_marg, n_top, K=K,
                                     init_cands=cands_init, n_iters=n_iters,
                                     seed=42, verbose=True)
    _, _, decoded, _ = viterbi_score(best_cands, id_stream, log_p, log_marg)
    print(f"  Recovered CE = {best_ce:.4f} (target: 3.59 = Latin true)", flush=True)
    print(f"  Sample: {decoded[:300]}", flush=True)
    sanity_ce = best_ce
    sanity_sample = decoded[:600]

    # ----- REAL B-system -----
    print(f"\n=== REAL B-system multi-cand SA, K={K} ===", flush=True)
    B = load_dialect("B")
    word_to_idx_B, top_words_B, n_cov_B, counts_B = build_vocab(B, n_top=n_top)
    id_stream_B = build_id_stream(B, word_to_idx_B)
    print(f"  {len(B)} tokens, top-{n_top} covers {n_cov_B}/{len(B)} "
          f"({100*n_cov_B/len(B):.1f}%)", flush=True)

    best_b_cands = None
    best_b_ce = float("inf")
    # Single restart only (each run ~15 min)
    for restart in range(1):
        cands_init_B = init_candidates(n_top, K, seed=1000 + restart)
        init_ce_B, _, _, _ = viterbi_score(cands_init_B, id_stream_B, log_p, log_marg)
        print(f"\n  Restart {restart}: init CE = {init_ce_B:.4f}", flush=True)
        cands, ce = sa_search(id_stream_B, log_p, log_marg, n_top, K=K,
                              init_cands=cands_init_B, n_iters=n_iters,
                              seed=2000 + restart, verbose=(restart == 0))
        print(f"    best CE = {ce:.4f}", flush=True)
        if ce < best_b_ce:
            best_b_ce = ce
            best_b_cands = cands

    print(f"\n  >>> B best CE under Latin = {best_b_ce:.4f}", flush=True)
    _, _, decoded_B, _ = viterbi_score(best_b_cands, id_stream_B, log_p, log_marg)
    print(f"  First 600 chars: {decoded_B[:600]}", flush=True)
    ce_B_ita, _, _, _ = viterbi_score(best_b_cands, id_stream_B, log_p_ita, log_marg_ita)
    print(f"  CE under Italian (same cands): {ce_B_ita:.4f}", flush=True)

    # show top word -> learned candidate sets
    print(f"\n  Top-20 B word candidate sets (learned):", flush=True)
    for v in range(20):
        w = top_words_B[v]
        sets = []
        for k in range(K):
            l1 = int(best_b_cands[v, k, 0])
            l2 = int(best_b_cands[v, k, 1])
            if l2 >= 0:
                sets.append(ALPHABET[l1] + ALPHABET[l2])
            else:
                sets.append(ALPHABET[l1])
        print(f"    {w:<14}  count={counts_B[w]:>4}  cands={sets}", flush=True)

    out = {
        "alphabet": ALPHABET,
        "n_top": n_top,
        "K": K,
        "sanity_ce": sanity_ce,
        "sanity_sample": sanity_sample,
        "B_best_ce_latin": best_b_ce,
        "B_best_ce_italian": ce_B_ita,
        "B_decoded_first_1500": decoded_B[:1500],
        "B_top_20_candidate_sets": [
            {
                "word": top_words_B[v],
                "count": counts_B[top_words_B[v]],
                "candidates": [
                    (ALPHABET[int(best_b_cands[v, k, 0])] +
                     ALPHABET[int(best_b_cands[v, k, 1])])
                    if best_b_cands[v, k, 1] >= 0
                    else ALPHABET[int(best_b_cands[v, k, 0])]
                    for k in range(K)
                ],
            }
            for v in range(20)
        ],
    }
    (ROOT / "em_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "em_decoded_B.txt").write_text(decoded_B, encoding="utf-8")
    print(f"\nWrote {ROOT/'em_results.json'}", flush=True)


if __name__ == "__main__":
    main()
