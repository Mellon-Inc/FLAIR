"""HMM-style Viterbi decoder over Greshko Naibbe candidates + permutation SA.

Phase 9 found that a single-assignment homophonic decoder (each Voynichese
word -> 1 fixed letter sequence) hits a 0.44 bit/letter floor above Latin
true even on synthetic Naibbe(Pliny), because Naibbe is genuinely homophonic:
the same glyph string (e.g. "dar") can encode different letters depending
on which of 6 tables was randomly drawn.

This decoder fixes that by allowing **multiple candidates per word** and
choosing per-occurrence using Viterbi:

  1. For each Voynichese word w, enumerate ALL Greshko-codebook decodings:
       - As a unigram: any (state=unigram, table, letter) entry whose glyph
         string equals w. Decoding = [letter].
       - As a bigram: any split w = p + s where p is a prefix entry and s
         is a suffix entry. Decoding = [letter_p, letter_s].
  2. Train a Latin character bigram LM on Pliny without word boundaries
     (matches the cipher's space-removal behaviour).
  3. Viterbi over the Voynichese token stream:
       state = last decoded letter
       transition = bigram log-prob under Latin LM
       emission = chosen candidate's letter chain
       Pick the path that maximises total log-likelihood.
  4. Optionally apply a global 23-letter permutation π to ALL Greshko
     letters before Viterbi, and run SA over π to find the best.
     (This combines Phase 8 alphabet permutation with Phase 9 multi-
     candidate decoding.)

Sanity expectation: synthetic Naibbe(Pliny) under identity permutation
should hit the Latin true floor (3.59 bits/letter) because Viterbi can
correctly disambiguate the table choices that the cipher made randomly.

Real Voynichese B: if Greshko's specific glyph strings match the actual
cipher (just permuted), CE will drop close to 3.59. If not, will plateau
above.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva  # noqa: E402

ALPHABET = list("abcdefghilmnopqrstuvxyz")
ABC_INDEX = {c: i for i, c in enumerate(ALPHABET)}
N = len(ALPHABET)


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


# ----------------- Greshko inverse codebook -----------------

def load_inverse_codebook():
    csv_path = DATA / "naibbe" / "naibbe_tables.csv"
    inv = defaultdict(list)
    with csv_path.open(encoding="utf-8-sig") as f:
        next(f)
        for line in f:
            line = line.strip()
            if not line:
                continue
            code, glyph = line.split(",", 1)
            state, table, letter = code.split("_", 2)
            inv[glyph].append((state, table, letter))
    return inv


def candidates_for(word: str, inv) -> list[tuple[int, ...]]:
    """Return all unique letter-index sequences this Voynichese word could
    decode to under Greshko's codebook (unigram OR bigram).
    """
    cands = set()
    # unigram
    for state, table, letter in inv.get(word, []):
        if state == "unigram":
            cands.add((ABC_INDEX[letter],))
    # bigram split
    for k in range(1, len(word)):
        p, s = word[:k], word[k:]
        prefixes = [(t, l) for st, t, l in inv.get(p, []) if st == "prefix"]
        suffixes = [(t, l) for st, t, l in inv.get(s, []) if st == "suffix"]
        for tp, lp in prefixes:
            for ts, ls in suffixes:
                cands.add((ABC_INDEX[lp], ABC_INDEX[ls]))
    return sorted(cands)


# ----------------- Latin bigram LM -----------------

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


# ----------------- Viterbi (per-token candidate selection) -----------------

def viterbi(tokens: list[str], inv, log_p: np.ndarray, log_marg: np.ndarray,
            perm: np.ndarray | None = None, debug: bool = False):
    """Find the best plaintext path through Greshko candidates.

    Returns (decoded_string, total_log_likelihood, n_letters, n_unmatched,
             per_token_decoding_indices).

    `perm` is an optional 23-letter permutation; if provided, every
    Greshko letter is replaced by perm[letter] before scoring.
    """
    if perm is None:
        perm = np.arange(N, dtype=np.int64)

    NEG_INF = -1e18

    # Per-token candidate cache (decoded letter sequences, AFTER perm)
    cand_cache: dict[str, list[tuple[int, ...]]] = {}

    def get_cands(w):
        if w not in cand_cache:
            raw = candidates_for(w, inv)
            cand_cache[w] = [tuple(int(perm[l]) for l in seq) for seq in raw]
        return cand_cache[w]

    # Viterbi DP: dp[L] = (best_log_p, backpointer_token_choice) ending in letter L
    # We process token by token. State = last emitted letter.
    # At BOS, "last letter" is None — handled with log_marg.

    # initial dp: only one virtual prev state "BOS"
    dp = np.full(N + 1, NEG_INF)  # extra slot N for BOS
    dp[N] = 0.0  # BOS prob = 1
    bp = []  # backpointer per token: list of dict L -> (prev_L, candidate_idx)

    n_unmatched = 0

    for t_idx, w in enumerate(tokens):
        cands = get_cands(w)
        if not cands:
            # OOV: emit nothing, propagate dp unchanged (state survives).
            # The next OK token will transition from the previous letter as
            # if the OOV token were absent. This loses the OOV's letters
            # from the decoded plaintext but keeps the path alive.
            n_unmatched += 1
            bp.append(("OOV", {}))
            continue

        new_dp = np.full(N, NEG_INF)
        new_bp = {}
        # For each candidate c with letters [l_0, l_1, ...]:
        for c_idx, letters in enumerate(cands):
            if len(letters) == 0:
                continue
            internal = 0.0
            for k in range(1, len(letters)):
                internal += log_p[letters[k - 1], letters[k]]
            f = letters[0]
            e = letters[-1]
            # transition from any previous state L (or BOS)
            best = dp[N] + log_marg[f] + internal
            best_prev = N
            scores_from_L = dp[:N] + log_p[:, f] + internal
            best_L = int(np.argmax(scores_from_L))
            best_score_from_L = scores_from_L[best_L]
            if best_score_from_L > best:
                best = best_score_from_L
                best_prev = best_L
            if best > new_dp[e]:
                new_dp[e] = best
                new_bp[e] = (best_prev, c_idx)

        dp = np.concatenate([new_dp, [NEG_INF]])  # BOS no longer reachable
        bp.append(("OK", new_bp))
        if debug and t_idx < 20:
            print(f"  token {t_idx}: {w!r} -> {len(cands)} cands; "
                  f"best dp = {new_dp.max():.2f}", flush=True)

    # Backtrack
    final_states = dp[:N]
    if final_states.max() <= NEG_INF / 2:
        return "", float("-inf"), 0, n_unmatched, []
    cur = int(np.argmax(final_states))
    total_loglik = float(final_states[cur])
    out_letters = []
    decisions = []
    # walk back through bp; OOV tokens don't change `cur`
    for i in range(len(tokens) - 1, -1, -1):
        kind, m = bp[i]
        if kind == "OOV":
            decisions.append(None)
            continue
        if cur < 0 or cur >= N or cur not in m:
            decisions.append(None)
            continue
        prev, c_idx = m[cur]
        cands = get_cands(tokens[i])
        letters = cands[c_idx]
        for L in reversed(letters):
            out_letters.append(L)
        decisions.append(c_idx)
        cur = prev if prev != N else -1  # -1 = BOS reached
    out_letters.reverse()
    decisions.reverse()
    decoded = "".join(ALPHABET[l] for l in out_letters)
    return decoded, total_loglik, len(out_letters), n_unmatched, decisions


# ----------------- SA over alphabet permutation -----------------

def sa_search_with_viterbi(tokens, inv, log_p, log_marg,
                            init_perm=None, n_iters=500, T_start=0.5,
                            T_end=0.01, seed=42, verbose=True):
    """Note: each Viterbi call is moderately expensive (~1s for 17K
    tokens), so we use FEW iterations. Use only if quick experiments
    suggest the permutation matters."""
    rng = random.Random(seed)
    perm = (np.array(init_perm, dtype=np.int64) if init_perm is not None
            else np.arange(N, dtype=np.int64))
    decoded, ll, n_letters, n_oov, _ = viterbi(tokens, inv, log_p, log_marg, perm)
    cur_ce = -ll / n_letters / math.log(2) if n_letters > 0 else float("inf")
    best_ce = cur_ce
    best_perm = perm.copy()

    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)
    t0 = time.time()
    for it in range(n_iters):
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        i, j = rng.sample(range(N), 2)
        perm[i], perm[j] = perm[j], perm[i]
        decoded, ll, n_letters, _, _ = viterbi(tokens, inv, log_p, log_marg, perm)
        new_ce = -ll / n_letters / math.log(2) if n_letters > 0 else float("inf")
        delta = new_ce - cur_ce
        if delta < 0 or rng.random() < math.exp(-delta / T):
            cur_ce = new_ce
            if cur_ce < best_ce:
                best_ce = cur_ce
                best_perm = perm.copy()
        else:
            perm[i], perm[j] = perm[j], perm[i]
        if verbose and (it + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  it {it+1:>4}/{n_iters} T={T:.4f} cur={cur_ce:.4f} "
                  f"best={best_ce:.4f} ({elapsed:.0f}s)", flush=True)
    return best_perm, best_ce


# ----------------- main -----------------

def main():
    print("Loading Greshko codebook...", flush=True)
    inv = load_inverse_codebook()

    print("Training Latin bigram LM...", flush=True)
    log_p, log_marg = train_bigram(DATA / "comparison" / "latin_pliny.txt")
    log_p_ita, log_marg_ita = train_bigram(DATA / "comparison" / "italian_dc.txt")

    # ----- SANITY 1: synthetic Naibbe(Pliny) under identity perm -----
    print("\n--- SANITY 1: Viterbi on synthetic Naibbe(Pliny), identity perm ---", flush=True)
    pliny = (DATA / "naibbe" / "naibbe_pliny_book16.txt") \
        .read_text(encoding="utf-8").split()
    print(f"  {len(pliny)} tokens", flush=True)
    decoded, ll, n_letters, n_oov, _ = viterbi(pliny, inv, log_p, log_marg)
    ce = -ll / n_letters / math.log(2)
    print(f"  decoded {n_letters} letters, {n_oov} OOV", flush=True)
    print(f"  CE under Latin = {ce:.4f}  (target: 3.59 = Latin true)", flush=True)
    print(f"  First 400 letters: {decoded[:400]}", flush=True)

    sanity_ce = ce
    sanity_sample = decoded[:600]

    # ----- REAL B-system Viterbi under identity -----
    print("\n--- Real B-system Viterbi under Greshko identity perm ---", flush=True)
    B = load_dialect("B")
    print(f"  {len(B)} tokens", flush=True)
    decoded_B, ll_B, n_letters_B, n_oov_B, _ = viterbi(B, inv, log_p, log_marg)
    ce_B = -ll_B / n_letters_B / math.log(2)
    print(f"  decoded {n_letters_B} letters, {n_oov_B} OOV", flush=True)
    print(f"  CE under Latin = {ce_B:.4f}", flush=True)
    print(f"  First 400 letters: {decoded_B[:400]}", flush=True)

    # also under Italian for comparison
    decoded_B_ita, ll_B_ita, n_B_ita, _, _ = viterbi(B, inv, log_p_ita, log_marg_ita)
    ce_B_ita = -ll_B_ita / n_B_ita / math.log(2) if n_B_ita > 0 else float("nan")
    print(f"  CE under Italian (separate Viterbi) = {ce_B_ita:.4f}", flush=True)

    # ----- SA over permutation (small budget, since each iter is expensive) -----
    print("\n--- Permutation SA over Viterbi (B, 100 iters) ---", flush=True)
    best_perm, best_ce = sa_search_with_viterbi(
        B, inv, log_p, log_marg, n_iters=100, seed=42, verbose=True)
    print(f"  >>> B permutation SA + Viterbi best CE = {best_ce:.4f}", flush=True)

    decoded_B_perm, ll_perm, n_perm, _, _ = viterbi(B, inv, log_p, log_marg,
                                                     perm=best_perm)
    print(f"  First 600 letters under best perm: {decoded_B_perm[:600]}", flush=True)
    print(f"  Permutation: {[ALPHABET[best_perm[i]] for i in range(N)]}", flush=True)

    out = {
        "alphabet": ALPHABET,
        "sanity": {
            "ce_synthetic_pliny_identity": sanity_ce,
            "first_600": sanity_sample,
        },
        "B_identity_perm_ce": ce_B,
        "B_decoded_identity_first_600": decoded_B[:600],
        "B_ce_italian": ce_B_ita,
        "B_perm_sa_best_ce": best_ce,
        "B_decoded_perm_sa_first_1500": decoded_B_perm[:1500],
        "B_best_perm": [ALPHABET[best_perm[i]] for i in range(N)],
    }
    (ROOT / "viterbi_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "viterbi_decoded_B.txt").write_text(decoded_B_perm, encoding="utf-8")
    print(f"\nWrote {ROOT/'viterbi_results.json'}", flush=True)


if __name__ == "__main__":
    main()
