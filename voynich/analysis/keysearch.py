"""MCMC / simulated-annealing search for the actual Voynichese cipher key.

Given the Phase-5 / Phase-7 hypothesis that Voynichese is the output of a
Naibbe-style cipher with a different key from Greshko's reconstruction,
this script searches over **23-letter alphabet permutations** π that
relabel Greshko's letters to the actual plaintext letters.

Algorithm:
  1. Precompute, for every Voynichese word in dialect B (and A), its canonical
     Greshko decoding — the most common (state, table) match — yielding a
     letter sequence in Greshko's 23-letter alphabet.
  2. Train a character-level bigram language model on real Latin (Pliny),
     concatenating all words into a single space-free stream so that the
     model's "boundaries" are merely letter→letter transitions (matching
     the cipher's space-removal behaviour).
  3. Score a candidate permutation π by computing the per-letter cross-entropy
     of (π applied to all decodings) under the Latin LM.
  4. Run simulated annealing over the symmetric group S_23. Move = swap two
     letters in π. Anneal temperature from 1.0 down to 0.005 over N iterations.
     Keep the best permutation seen.
  5. Repeat from multiple random restarts (and from identity).

Pre-flight sanity: when applied to synthetic Naibbe(Pliny), MCMC should
recover identity (or near-identity) permutation, with cross-entropy
≈ 4.0 bits/letter.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva  # noqa: E402

ALPHABET = list("abcdefghilmnopqrstuvxyz")  # Naibbe 23-letter alphabet
ABC_INDEX = {c: i for i, c in enumerate(ALPHABET)}

# --------------- inverse codebook ----------------

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


# --------------- canonical Greshko decoding ----------------

# Preferred table order (mirrors Naibbe 78-card deck weights, alpha-heavy)
TABLE_PREF = ["alpha", "beta1", "beta2", "beta3", "gamma1", "gamma2"]
TABLE_RANK = {t: i for i, t in enumerate(TABLE_PREF)}


def canonical_decode(word: str, inv) -> tuple[str, ...]:
    """Return the most-likely Greshko decoding of `word` as a tuple of letters
    in Greshko's 23-letter alphabet.

    Strategy: prefer unigram interpretation if available (it's the more
    common Naibbe state). Within unigram or bigram, prefer the alpha table.
    Returns empty tuple if no match.
    """
    # unigram
    unigrams = [(t, l) for st, t, l in inv.get(word, []) if st == "unigram"]
    if unigrams:
        unigrams.sort(key=lambda x: TABLE_RANK[x[0]])
        return (unigrams[0][1],)

    # bigram: try all splits, prefer balanced split (closer to len/2)
    candidates = []
    for k in range(1, len(word)):
        p, s = word[:k], word[k:]
        prefixes = [(t, l) for st, t, l in inv.get(p, []) if st == "prefix"]
        suffixes = [(t, l) for st, t, l in inv.get(s, []) if st == "suffix"]
        for tp, lp in prefixes:
            for ts, ls in suffixes:
                # prefer alpha tables
                rank = TABLE_RANK[tp] + TABLE_RANK[ts]
                # also prefer balanced split
                imbalance = abs(k - len(word) // 2)
                candidates.append((rank, imbalance, lp, ls))
    if not candidates:
        return ()
    candidates.sort()
    return (candidates[0][2], candidates[0][3])


def precompute_decodings(words: list[str], inv) -> tuple[list[list[int]], int]:
    """For each Voynichese word, produce its canonical Greshko letter sequence
    encoded as integer indices into ALPHABET. Empty tuple if unmatched.
    Returns (decodings, n_unmatched).
    """
    out = []
    n_unmatched = 0
    for w in words:
        letters = canonical_decode(w, inv)
        if not letters:
            n_unmatched += 1
            out.append([])
            continue
        out.append([ABC_INDEX[L] for L in letters])
    return out, n_unmatched


# --------------- Latin bigram LM (on space-free letter stream) ----------------

def normalise(text: str) -> str:
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("w", "uu").replace("j", "i").replace("k", "c")
    text = "".join(c for c in text if c in ALPHABET)
    return text


def train_bigram_matrix(corpus_path: Path, smooth: float = 0.5) -> list[list[float]]:
    """Returns log_p[a][b] = log P(b|a) with Laplace smoothing.

    Training is on the **concatenated** letter stream (no word boundaries),
    matching the cipher's space-removal behaviour.
    """
    text = corpus_path.read_text(encoding="utf-8", errors="ignore")
    letters = normalise(text)
    n = len(ALPHABET)
    counts = [[0] * n for _ in range(n)]
    init_counts = [0] * n  # P(b|^) approximation: use marginal frequency
    for a, b in zip(letters[:-1], letters[1:]):
        counts[ABC_INDEX[a]][ABC_INDEX[b]] += 1
    # marginal letter frequency for "BOS" handling
    marg = Counter(letters)
    log_p = [[0.0] * n for _ in range(n)]
    for i in range(n):
        row_sum = sum(counts[i]) + smooth * n
        for j in range(n):
            log_p[i][j] = math.log((counts[i][j] + smooth) / row_sum)
    # marginal log-prob (used as start-of-stream emission prob)
    total_marg = sum(marg.values()) + smooth * n
    log_marg = [math.log((marg.get(c, 0) + smooth) / total_marg) for c in ALPHABET]
    return log_p, log_marg


# --------------- scoring ----------------

def score_permutation(perm: list[int], decodings: list[list[int]],
                      log_p: list[list[float]],
                      log_marg: list[float]) -> tuple[float, int]:
    """Per-letter cross-entropy (bits/letter, lower=better).

    `perm` is a permutation array: perm[g] = π(g) = the actual letter (index)
    that Greshko-letter g really stands for.

    For each Voynichese-word decoding [g0, g1, ...], we map g_i -> π(g_i)
    and score the resulting concatenated stream under log_p (bigram LM).
    """
    score = 0.0
    n = 0
    prev = -1  # -1 => use marginal
    for letters in decodings:
        for g in letters:
            mapped = perm[g]
            if prev == -1:
                score += log_marg[mapped]
            else:
                score += log_p[prev][mapped]
            prev = mapped
            n += 1
    if n == 0:
        return float("inf"), 0
    return -score / n / math.log(2), n  # bits/letter


def apply_perm(perm: list[int], decodings: list[list[int]]) -> str:
    out = []
    for letters in decodings:
        for g in letters:
            out.append(ALPHABET[perm[g]])
        out.append(" ")
    return "".join(out)


# --------------- simulated annealing ----------------

def sa_search(decodings, log_p, log_marg, n_iters=80000,
              T_start=1.0, T_end=0.005, init_perm=None, seed=42, verbose=True):
    rng = random.Random(seed)
    n = len(ALPHABET)
    if init_perm is None:
        perm = list(range(n))
    else:
        perm = list(init_perm)
    best_perm = list(perm)
    cur_ce, n_letters = score_permutation(perm, decodings, log_p, log_marg)
    best_ce = cur_ce

    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)

    accepts = 0
    rejects = 0
    last_print = time.time()
    for it in range(n_iters):
        # log-linear cooling
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        # propose: swap two distinct positions
        i, j = rng.sample(range(n), 2)
        perm[i], perm[j] = perm[j], perm[i]
        new_ce, _ = score_permutation(perm, decodings, log_p, log_marg)
        delta = new_ce - cur_ce  # bits/letter; positive = worse
        if delta < 0 or rng.random() < math.exp(-delta / T):
            cur_ce = new_ce
            accepts += 1
            if cur_ce < best_ce:
                best_ce = cur_ce
                best_perm = list(perm)
        else:
            perm[i], perm[j] = perm[j], perm[i]  # revert
            rejects += 1
        if verbose and time.time() - last_print > 5:
            print(f"  iter {it:>6}  T={T:.4f}  cur_ce={cur_ce:.4f}  best_ce={best_ce:.4f}  "
                  f"accepts={accepts} rejects={rejects}")
            last_print = time.time()
    if verbose:
        print(f"  done. best_ce={best_ce:.4f} accepts={accepts} rejects={rejects}")
    return best_perm, best_ce, n_letters


# --------------- A/B subcorpora ----------------

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


# --------------- main ----------------

def main():
    print("Loading inverse codebook...")
    inv = load_inverse_codebook()

    print("Training Latin bigram LM (no word boundaries)...")
    latin_log_p, latin_log_marg = train_bigram_matrix(
        DATA / "comparison" / "latin_pliny.txt")
    italian_log_p, italian_log_marg = train_bigram_matrix(
        DATA / "comparison" / "italian_dc.txt")
    finnish_log_p, finnish_log_marg = train_bigram_matrix(
        DATA / "comparison" / "finnish_bible.txt")
    english_log_p, english_log_marg = train_bigram_matrix(
        DATA / "comparison" / "english_pp_clean.txt")

    # ---- pre-flight sanity: Naibbe(Pliny) under identity perm ----
    print("\n--- Sanity: Naibbe(Pliny) decoded with identity permutation ---")
    pliny_naibbe = (DATA / "naibbe" / "naibbe_pliny_book16.txt") \
        .read_text(encoding="utf-8").split()
    pliny_decodings, pliny_unm = precompute_decodings(pliny_naibbe, inv)
    ce_id, n_lat = score_permutation(list(range(len(ALPHABET))),
                                      pliny_decodings, latin_log_p, latin_log_marg)
    print(f"  {len(pliny_naibbe)} tokens, {pliny_unm} unmatched, "
          f"{n_lat} letters, CE under Latin = {ce_id:.4f} bits/letter (identity perm)")

    # ---- MCMC sanity: starting from random perm, can we recover identity
    #      cross-entropy on Naibbe(Pliny)?
    print("\n--- MCMC sanity: random perm -> recover good CE on Naibbe(Pliny) ---")
    rng = random.Random(12345)
    random_perm = list(range(len(ALPHABET)))
    rng.shuffle(random_perm)
    print(f"  Initial random perm: {[ALPHABET[random_perm[i]] for i in range(len(ALPHABET))]}")
    ce_init, _ = score_permutation(random_perm, pliny_decodings,
                                    latin_log_p, latin_log_marg)
    print(f"  Initial random-perm CE = {ce_init:.4f}")
    best_perm, best_ce, _ = sa_search(
        pliny_decodings[:5000], latin_log_p, latin_log_marg,
        n_iters=30000, init_perm=random_perm, seed=1, verbose=True)
    print(f"  Recovered perm: {[ALPHABET[best_perm[i]] for i in range(len(ALPHABET))]}")
    print(f"  Recovered CE = {best_ce:.4f}")
    sample = apply_perm(best_perm, pliny_decodings[:200])
    print(f"  Decoded sample: {sample[:300]}")

    # ---- B-system MCMC under Latin LM ----
    print("\n--- B-system MCMC search under Latin LM ---")
    B = load_dialect("B")
    B_decodings, B_unm = precompute_decodings(B, inv)
    print(f"  {len(B)} Voynichese words, {B_unm} unmatched")

    # multiple restarts; take the best
    best_overall_perm = None
    best_overall_ce = float("inf")
    for restart in range(4):
        if restart == 0:
            init = list(range(len(ALPHABET)))  # identity (Greshko)
            label = "identity"
        else:
            init = list(range(len(ALPHABET)))
            rng = random.Random(100 + restart)
            rng.shuffle(init)
            label = f"random{restart}"
        print(f"\n  Restart {restart} ({label}):")
        ce_init, _ = score_permutation(init, B_decodings,
                                        latin_log_p, latin_log_marg)
        print(f"    initial CE = {ce_init:.4f}")
        bp, bc, _ = sa_search(B_decodings, latin_log_p, latin_log_marg,
                              n_iters=80000, init_perm=init,
                              seed=2000 + restart, verbose=False)
        print(f"    best CE = {bc:.4f}")
        if bc < best_overall_ce:
            best_overall_ce = bc
            best_overall_perm = bp

    print(f"\n  >>> Best B-MCMC permutation:")
    perm = best_overall_perm
    print(f"    Greshko-letter -> recovered-letter map:")
    for i, c in enumerate(ALPHABET):
        print(f"      {c} -> {ALPHABET[perm[i]]}")
    print(f"    best CE under Latin = {best_overall_ce:.4f} bits/letter")

    # score under all four LMs
    ce_lat, _ = score_permutation(perm, B_decodings, latin_log_p, latin_log_marg)
    ce_ita, _ = score_permutation(perm, B_decodings, italian_log_p, italian_log_marg)
    ce_fin, _ = score_permutation(perm, B_decodings, finnish_log_p, finnish_log_marg)
    ce_eng, _ = score_permutation(perm, B_decodings, english_log_p, english_log_marg)
    print(f"    CE under Latin   = {ce_lat:.4f}")
    print(f"    CE under Italian = {ce_ita:.4f}")
    print(f"    CE under Finnish = {ce_fin:.4f}")
    print(f"    CE under English = {ce_eng:.4f}")

    decoded_B = apply_perm(perm, B_decodings)
    print(f"\n  First 600 decoded characters of B (with spaces between Voynich-words):")
    print(f"    {decoded_B[:600]}")

    # ---- A-system MCMC ----
    print("\n--- A-system MCMC search under Latin LM ---")
    A = load_dialect("A")
    A_decodings, A_unm = precompute_decodings(A, inv)
    print(f"  {len(A)} words, {A_unm} unmatched")
    best_a_perm, best_a_ce, _ = sa_search(
        A_decodings, latin_log_p, latin_log_marg,
        n_iters=80000, seed=3000, verbose=False)
    decoded_A = apply_perm(best_a_perm, A_decodings)
    print(f"  best CE under Latin = {best_a_ce:.4f}")
    ce_a_ita, _ = score_permutation(best_a_perm, A_decodings, italian_log_p, italian_log_marg)
    print(f"  best perm CE under Italian = {ce_a_ita:.4f}")
    print(f"  First 600 chars: {decoded_A[:600]}")

    # ---- save ----
    out = {
        "alphabet": ALPHABET,
        "sanity_pliny_identity_ce": ce_id,
        "B_best_perm": [ALPHABET[perm[i]] for i in range(len(ALPHABET))],
        "B_best_perm_indices": perm,
        "B_ce_latin": ce_lat,
        "B_ce_italian": ce_ita,
        "B_ce_finnish": ce_fin,
        "B_ce_english": ce_eng,
        "B_decoded_first_600": decoded_B[:600],
        "A_best_perm": [ALPHABET[best_a_perm[i]] for i in range(len(ALPHABET))],
        "A_ce_latin": best_a_ce,
        "A_ce_italian": ce_a_ita,
        "A_decoded_first_600": decoded_A[:600],
    }
    (ROOT / "keysearch_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "keysearch_decoded_B.txt").write_text(decoded_B, encoding="utf-8")
    (ROOT / "keysearch_decoded_A.txt").write_text(decoded_A, encoding="utf-8")
    print(f"\nWrote {ROOT/'keysearch_results.json'}")


if __name__ == "__main__":
    main()
