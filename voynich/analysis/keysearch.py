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

import numpy as np

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


def train_bigram_matrix(corpus_path: Path, smooth: float = 0.5):
    """Returns (log_p, log_marg) as numpy arrays.

    log_p[a, b] = log P(b | a). Trained on the **concatenated** letter
    stream (no word boundaries), matching the cipher's space-removal
    behaviour.
    """
    text = corpus_path.read_text(encoding="utf-8", errors="ignore")
    letters = normalise(text)
    n = len(ALPHABET)
    counts = np.zeros((n, n), dtype=np.float64)
    idxs = np.array([ABC_INDEX[c] for c in letters], dtype=np.int64)
    np.add.at(counts, (idxs[:-1], idxs[1:]), 1.0)
    row_sums = counts.sum(axis=1) + smooth * n
    log_p = np.log((counts + smooth) / row_sums[:, None])
    marg = np.bincount(idxs, minlength=n).astype(np.float64)
    log_marg = np.log((marg + smooth) / (marg.sum() + smooth * n))
    return log_p, log_marg


# --------------- scoring ----------------

def flatten_decodings(decodings: list[list[int]]) -> np.ndarray:
    """Concatenate all decoded letters into a single int32 stream (we ignore
    Voynich-word boundaries in scoring, matching cipher's destroyed plaintext
    spaces)."""
    parts = [np.array(d, dtype=np.int32) for d in decodings if d]
    if not parts:
        return np.zeros(0, dtype=np.int32)
    return np.concatenate(parts)


def score_perm_fast(perm_arr: np.ndarray, dec_flat: np.ndarray,
                    log_p: np.ndarray, log_marg: np.ndarray) -> float:
    """Vectorised per-letter cross-entropy (bits/letter, lower=better)."""
    n = dec_flat.size
    if n == 0:
        return float("inf")
    mapped = perm_arr[dec_flat]
    if n == 1:
        total = log_marg[mapped[0]]
    else:
        total = log_marg[mapped[0]] + log_p[mapped[:-1], mapped[1:]].sum()
    return -float(total) / n / math.log(2)


def apply_perm_str(perm_arr: np.ndarray, decodings: list[list[int]]) -> str:
    """Render the permuted decodings as a string with spaces between
    Voynichese-word groups."""
    out = []
    for letters in decodings:
        if letters:
            out.append("".join(ALPHABET[perm_arr[g]] for g in letters))
        out.append(" ")
    return "".join(out)


# --------------- simulated annealing ----------------

def sa_search(dec_flat: np.ndarray, log_p: np.ndarray, log_marg: np.ndarray,
              n_iters: int = 80000, T_start: float = 0.5, T_end: float = 0.005,
              init_perm=None, seed: int = 42, verbose: bool = True):
    rng = random.Random(seed)
    n = len(ALPHABET)
    perm = np.array(list(range(n)) if init_perm is None else init_perm,
                    dtype=np.int64)
    best_perm = perm.copy()
    cur_ce = score_perm_fast(perm, dec_flat, log_p, log_marg)
    best_ce = cur_ce

    log_T_start = math.log(T_start)
    log_T_end = math.log(T_end)

    accepts = 0
    rejects = 0
    last_print = time.time()
    t0 = time.time()
    for it in range(n_iters):
        T = math.exp(log_T_start + (log_T_end - log_T_start) * it / n_iters)
        i, j = rng.sample(range(n), 2)
        perm[i], perm[j] = perm[j], perm[i]
        new_ce = score_perm_fast(perm, dec_flat, log_p, log_marg)
        delta = new_ce - cur_ce
        if delta < 0 or rng.random() < math.exp(-delta / T):
            cur_ce = new_ce
            accepts += 1
            if cur_ce < best_ce:
                best_ce = cur_ce
                best_perm = perm.copy()
        else:
            perm[i], perm[j] = perm[j], perm[i]
            rejects += 1
        if verbose and time.time() - last_print > 4:
            print(f"  iter {it:>6}  T={T:.4f}  cur={cur_ce:.4f}  best={best_ce:.4f}  "
                  f"accepts={accepts} rejects={rejects}  "
                  f"({(it+1)/(time.time()-t0):.0f} it/s)", flush=True)
            last_print = time.time()
    if verbose:
        print(f"  done in {time.time()-t0:.1f}s. best_ce={best_ce:.4f} "
              f"accepts={accepts} rejects={rejects}", flush=True)
    return best_perm, best_ce


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

    print("Training bigram LMs (no word boundaries)...", flush=True)
    LM = {}
    for name, fname in [("Latin", "latin_pliny.txt"),
                        ("Italian", "italian_dc.txt"),
                        ("Finnish", "finnish_bible.txt"),
                        ("English", "english_pp_clean.txt")]:
        LM[name] = train_bigram_matrix(DATA / "comparison" / fname)
        print(f"  {name} trained", flush=True)

    n = len(ALPHABET)
    identity_perm = np.arange(n, dtype=np.int64)

    # ---- pre-flight sanity ----
    print("\n--- Sanity: Naibbe(Pliny) decoded with identity permutation ---", flush=True)
    pliny_naibbe = (DATA / "naibbe" / "naibbe_pliny_book16.txt") \
        .read_text(encoding="utf-8").split()
    pliny_decodings, pliny_unm = precompute_decodings(pliny_naibbe, inv)
    pliny_flat = flatten_decodings(pliny_decodings)
    ce_id = score_perm_fast(identity_perm, pliny_flat, *LM["Latin"])
    print(f"  {len(pliny_naibbe)} tokens, {pliny_unm} unmatched, "
          f"{pliny_flat.size} letters, CE under Latin = {ce_id:.4f} bits/letter "
          f"(identity perm)", flush=True)

    # ---- MCMC sanity: random perm -> recover good CE on Naibbe(Pliny) ----
    print("\n--- MCMC sanity: random perm -> recover good CE on Naibbe(Pliny) ---", flush=True)
    rng = random.Random(12345)
    random_perm = list(range(n))
    rng.shuffle(random_perm)
    print(f"  Initial random perm: {[ALPHABET[random_perm[i]] for i in range(n)]}", flush=True)
    ce_init = score_perm_fast(np.array(random_perm), pliny_flat, *LM["Latin"])
    print(f"  Initial random-perm CE = {ce_init:.4f}", flush=True)
    sanity_perm, sanity_ce = sa_search(
        pliny_flat[:60000], LM["Latin"][0], LM["Latin"][1],
        n_iters=40000, init_perm=random_perm, seed=1, verbose=True)
    print(f"  Recovered perm: {[ALPHABET[sanity_perm[i]] for i in range(n)]}", flush=True)
    print(f"  Recovered CE = {sanity_ce:.4f}", flush=True)
    sample = apply_perm_str(sanity_perm, pliny_decodings[:120])
    print(f"  Decoded sample: {sample[:300]}", flush=True)

    # ---- B-system MCMC ----
    print("\n--- B-system MCMC search under Latin LM ---", flush=True)
    B = load_dialect("B")
    B_decodings, B_unm = precompute_decodings(B, inv)
    B_flat = flatten_decodings(B_decodings)
    print(f"  {len(B)} Voynichese words, {B_unm} unmatched, "
          f"{B_flat.size} decoded letters", flush=True)

    best_perm = None
    best_ce = float("inf")
    for restart in range(4):
        if restart == 0:
            init = list(range(n))
            label = "identity"
        else:
            init = list(range(n))
            rng = random.Random(100 + restart)
            rng.shuffle(init)
            label = f"random{restart}"
        ce_i = score_perm_fast(np.array(init), B_flat, *LM["Latin"])
        print(f"\n  Restart {restart} ({label}): initial CE = {ce_i:.4f}", flush=True)
        bp, bc = sa_search(B_flat, LM["Latin"][0], LM["Latin"][1],
                           n_iters=60000, init_perm=init,
                           seed=2000 + restart, verbose=(restart == 0))
        print(f"    best CE = {bc:.4f}", flush=True)
        if bc < best_ce:
            best_ce = bc
            best_perm = bp

    print(f"\n  >>> Best B-MCMC permutation:", flush=True)
    print(f"    Greshko-letter -> recovered-letter map:")
    for i, c in enumerate(ALPHABET):
        print(f"      {c} -> {ALPHABET[best_perm[i]]}")
    print(f"    best CE under Latin = {best_ce:.4f} bits/letter", flush=True)

    ce_lat = score_perm_fast(best_perm, B_flat, *LM["Latin"])
    ce_ita = score_perm_fast(best_perm, B_flat, *LM["Italian"])
    ce_fin = score_perm_fast(best_perm, B_flat, *LM["Finnish"])
    ce_eng = score_perm_fast(best_perm, B_flat, *LM["English"])
    print(f"    CE under Latin   = {ce_lat:.4f}", flush=True)
    print(f"    CE under Italian = {ce_ita:.4f}", flush=True)
    print(f"    CE under Finnish = {ce_fin:.4f}", flush=True)
    print(f"    CE under English = {ce_eng:.4f}", flush=True)

    decoded_B = apply_perm_str(best_perm, B_decodings)
    print(f"\n  First 600 decoded characters of B:")
    print(f"    {decoded_B[:600]}", flush=True)

    # ---- A-system MCMC ----
    print("\n--- A-system MCMC search under Latin LM ---", flush=True)
    A = load_dialect("A")
    A_decodings, A_unm = precompute_decodings(A, inv)
    A_flat = flatten_decodings(A_decodings)
    print(f"  {len(A)} words, {A_unm} unmatched, {A_flat.size} letters", flush=True)
    best_a_perm = None
    best_a_ce = float("inf")
    for restart in range(3):
        init = list(range(n))
        if restart > 0:
            rng = random.Random(3000 + restart)
            rng.shuffle(init)
        bp, bc = sa_search(A_flat, LM["Latin"][0], LM["Latin"][1],
                           n_iters=60000, init_perm=init,
                           seed=3500 + restart, verbose=False)
        print(f"  restart {restart}: best CE = {bc:.4f}", flush=True)
        if bc < best_a_ce:
            best_a_ce = bc
            best_a_perm = bp
    print(f"  >>> A best CE Latin = {best_a_ce:.4f}", flush=True)
    ce_a_ita = score_perm_fast(best_a_perm, A_flat, *LM["Italian"])
    ce_a_fin = score_perm_fast(best_a_perm, A_flat, *LM["Finnish"])
    print(f"  A best perm CE Italian = {ce_a_ita:.4f}, Finnish = {ce_a_fin:.4f}", flush=True)
    decoded_A = apply_perm_str(best_a_perm, A_decodings)
    print(f"  First 600 chars: {decoded_A[:600]}", flush=True)

    out = {
        "alphabet": ALPHABET,
        "sanity_pliny_identity_ce": ce_id,
        "sanity_recovered_ce": sanity_ce,
        "sanity_recovered_perm": [ALPHABET[sanity_perm[i]] for i in range(n)],
        "B_best_perm_letters": [ALPHABET[best_perm[i]] for i in range(n)],
        "B_best_perm_indices": [int(x) for x in best_perm],
        "B_ce_latin": ce_lat, "B_ce_italian": ce_ita,
        "B_ce_finnish": ce_fin, "B_ce_english": ce_eng,
        "B_decoded_first_600": decoded_B[:600],
        "A_best_perm_letters": [ALPHABET[best_a_perm[i]] for i in range(n)],
        "A_ce_latin": best_a_ce, "A_ce_italian": ce_a_ita,
        "A_ce_finnish": ce_a_fin,
        "A_decoded_first_600": decoded_A[:600],
    }
    (ROOT / "keysearch_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "keysearch_decoded_B.txt").write_text(decoded_B, encoding="utf-8")
    (ROOT / "keysearch_decoded_A.txt").write_text(decoded_A, encoding="utf-8")
    print(f"\nWrote {ROOT/'keysearch_results.json'}")


if __name__ == "__main__":
    main()
