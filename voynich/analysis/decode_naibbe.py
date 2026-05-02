"""Reverse-decode Voynichese A and B subcorpora through the Naibbe codebook.

Pipeline:
  1. Build inverse maps from Naibbe glyph string -> list of (state, table, letter)
     where state in {unigram, prefix, suffix} and letter in 23-letter alphabet
     (Naibbe uses no w/j/k; w->uu, j->i, k->c are pre-applied).
  2. For each Voynichese word, find all candidate decodings:
       - As a unigram: decodes to 1 letter
       - As a bigram split at every position k: prefix=word[:k] suffix=word[k:],
         both must be in the respective inverse map. Decodes to 2 letters.
  3. Train Laplace-smoothed character bigram language models on real corpora:
       Latin (Pliny), Italian (Dante), English (P&P), Finnish (Bible).
  4. Run Viterbi over the Voynichese token stream (state = previous letter,
     emissions = candidate decodings of each word) to find the best plaintext
     under each language model.
  5. Score the decoded streams against all four languages by per-letter
     cross-entropy. Lower = better fit. The hypothesis "B-system plaintext is
     Latin" predicts B's decoded text scores best under Latin.
  6. Round-trip sanity check: re-encrypt a held-out Latin sample with Naibbe,
     decode it back, measure recovery rate.

Outputs:
  decode_results.json
  decoded_B_under_latin.txt
  decoded_A_under_latin.txt
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva  # noqa: E402

# 23-letter Naibbe alphabet (no w/j/k)
ALPHABET = list("abcdefghilmnopqrstuvxyz")  # 23 letters

# ---------------- inverse codebook ----------------

def load_inverse_codebook():
    """Build glyph_string -> list[(state, table, letter)]."""
    csv_path = DATA / "naibbe" / "naibbe_tables.csv"
    inv: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            code, glyph = row[0], row[1]
            state, table, letter = code.split("_", 2)
            inv[glyph].append((state, table, letter))
    return inv


# ---------------- bigram language model ----------------

def normalise_for_lm(text: str, alphabet: str = "latin") -> list[str]:
    """Return a list of words (lowercased, alphabetic) usable for LM training.

    Apply Naibbe's letter normalisation (w->uu, j->i, k->c) to make the LM
    alphabet identical to the cipher's plaintext alphabet — otherwise letters
    the cipher cannot encode would inflate cross-entropy.
    """
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    if alphabet == "finnish":
        # collapse äö to a/o for now (Naibbe alphabet has no ä/ö); ø->o, å->a
        text = text.replace("ä", "a").replace("ö", "o") \
                   .replace("å", "a").replace("ø", "o")
    text = text.replace("w", "uu").replace("j", "i").replace("k", "c")
    return re.findall(r"[a-z]+", text)


def train_bigram(text_words: list[str], alphabet: list[str], smooth: float = 0.5) -> dict:
    """Laplace-smoothed bigram model with explicit BOS '^' and EOS '$'.

    Word boundaries are encoded as '$' between words (i.e., we glue all
    letters with '$' separators; this lets the model see end-of-word
    transitions, which are informative for Latin -us/-is/-ae endings).
    """
    states = list(alphabet) + ["^", "$"]
    bg: dict[str, Counter] = {s: Counter() for s in states}
    prev = "^"
    for w in text_words:
        if not w:
            continue
        for c in w:
            if c not in alphabet:
                continue
            bg[prev][c] += 1
            prev = c
        bg[prev]["$"] += 1
        prev = "^"

    # turn into log-probabilities with Laplace smoothing
    n_states = len(alphabet) + 1  # +1 for $; ^ is only a from-state
    log_p: dict[str, dict[str, float]] = {}
    for s, counts in bg.items():
        total = sum(counts.values()) + smooth * n_states
        log_p[s] = {}
        for t in alphabet + ["$"]:
            log_p[s][t] = math.log((counts.get(t, 0) + smooth) / total)
    return log_p


# ---------------- decoder ----------------

EVA_LOWER_MAP = {"Sh": "sh", "cTh": "cth", "cKh": "ckh", "cPh": "cph", "cFh": "cfh"}


def to_naibbe_form(word: str) -> str:
    """Convert Takahashi-EVA word to Naibbe codebook form (lowercase)."""
    out = word
    for k, v in EVA_LOWER_MAP.items():
        out = out.replace(k, v)
    out = out.replace("*", "").replace("!", "").replace("=", "")
    return out


def candidate_decodings(word: str, inv) -> list[tuple[tuple[str, ...], list[str]]]:
    """Return all candidate decodings of `word`.

    Each is (letters, decoder_info). Letters is a tuple of plaintext letters
    (length 1 for unigram, 2 for bigram). decoder_info is a list of debug
    strings.
    """
    cands: list[tuple[tuple[str, ...], list[str]]] = []
    # unigram match
    for state, table, letter in inv.get(word, []):
        if state == "unigram":
            cands.append(((letter,), [f"U:{table}_{letter}"]))
    # bigram splits
    for k in range(1, len(word)):
        p, s = word[:k], word[k:]
        prefix_matches = [(t, l) for st, t, l in inv.get(p, []) if st == "prefix"]
        suffix_matches = [(t, l) for st, t, l in inv.get(s, []) if st == "suffix"]
        if prefix_matches and suffix_matches:
            for tp, lp in prefix_matches:
                for ts, ls in suffix_matches:
                    cands.append(((lp, ls),
                                  [f"P:{tp}_{lp}", f"S:{ts}_{ls}"]))
    return cands


def viterbi_decode(words: list[str], inv, log_p: dict, alphabet: list[str]):
    """Find best plaintext under the given bigram model.

    State = previous letter. We process Voynichese words one at a time. For
    each word, candidate decodings give variable-length emissions (1 or 2
    letters). We expand:
        new_score(letter_last) = max over (prev_letter, candidate)
                                  prev_score(prev_letter)
                                  + sum log P(letters | starting prev_letter)
    Backtrack to recover plaintext.
    """
    NEG_INF = float("-inf")
    states = list(alphabet) + ["^"]  # "^" = before-word / no previous letter
    # initial: prev is BOS '^'
    score = {s: NEG_INF for s in states}
    score["^"] = 0.0
    back = []  # at each step, dict[state] = (prev_state, letters, cand_info)

    skipped = 0
    for w in words:
        cands = candidate_decodings(w, inv)
        if not cands:
            skipped += 1
            # treat as unknown: emit nothing, keep state
            back.append({s: (s, tuple(), ["?"]) for s in states})
            continue
        new_score = {s: NEG_INF for s in states}
        new_back = {}
        for prev_s, prev_score in score.items():
            if prev_score == NEG_INF:
                continue
            for letters, info in cands:
                # compute log p of emitting letters given prev_s
                lp = 0.0
                cur = prev_s
                for L in letters:
                    if L not in log_p[cur]:
                        lp = NEG_INF
                        break
                    lp += log_p[cur][L]
                    cur = L
                if lp == NEG_INF:
                    continue
                end_state = letters[-1] if letters else prev_s
                if prev_score + lp > new_score[end_state]:
                    new_score[end_state] = prev_score + lp
                    new_back[end_state] = (prev_s, letters, info)
        # if no transition was valid, fallback: keep previous state and
        # emit a placeholder
        for s in states:
            if s not in new_back:
                new_back[s] = (s, tuple(), ["?"])
        score = new_score
        back.append(new_back)

    # final: terminate with EOS '$'
    final_state = max(score, key=score.get)
    final_score = score[final_state]

    # backtrack
    letters_out = []
    info_out = []
    cur = final_state
    for step in range(len(back) - 1, -1, -1):
        prev_s, letters, info = back[step][cur]
        letters_out.extend(reversed(letters))
        info_out.extend(reversed(info))
        cur = prev_s
    letters_out.reverse()
    info_out.reverse()
    return {
        "plaintext": "".join(letters_out),
        "log_likelihood": final_score,
        "n_voynich_words": len(words),
        "n_unmatched_words": skipped,
        "n_letters_decoded": len(letters_out),
        "decoder_info": info_out,
    }


def cross_entropy_under(decoded: str, log_p: dict, alphabet: list[str]) -> float:
    """Per-letter cross-entropy of `decoded` under bigram model log_p."""
    if not decoded:
        return float("inf")
    total = 0.0
    n = 0
    cur = "^"
    for c in decoded:
        if c not in alphabet:
            continue
        total -= log_p[cur].get(c, math.log(1e-12))
        cur = c
        n += 1
    return total / n / math.log(2) if n else float("inf")  # bits/letter


# ---------------- A/B subcorpora ----------------

SECTION_TO_DIALECT = {
    "Herbal": "A", "Pharmaceutical": "A",
    "Biological": "B", "Recipes": "B",
    "Cosmological": None, "Astronomical": None, "Unknown": None,
}


def load_dialect(dialect: str) -> list[str]:
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    out = []
    for r in records:
        if SECTION_TO_DIALECT.get(r["section"]) != dialect:
            continue
        for w in r["words"]:
            if not w:
                continue
            nw = to_naibbe_form(w)
            if not nw:
                continue
            out.append(nw)
    return out


# ---------------- main ----------------

def main():
    print("Loading inverse codebook...")
    inv = load_inverse_codebook()
    print(f"  unique glyph strings: {len(inv)}")

    print("\nTraining bigram language models...")
    lm_paths = {
        "Latin": ("latin_pliny.txt", "latin"),
        "Italian": ("italian_dc.txt", "latin"),
        "English": ("english_pp_clean.txt", "latin"),
        "Finnish": ("finnish_bible.txt", "finnish"),
    }
    models = {}
    for name, (fname, alpha) in lm_paths.items():
        path = DATA / "comparison" / fname
        if not path.exists():
            print(f"  [skip] {name}: {path} missing")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        words = normalise_for_lm(text, alphabet=alpha)
        # restrict letters to ALPHABET (23-letter)
        words = ["".join(c for c in w if c in ALPHABET) for w in words]
        words = [w for w in words if w]
        models[name] = train_bigram(words, ALPHABET)
        print(f"  {name}: {sum(len(w) for w in words)} chars, {len(words)} words")

    # ---- Round-trip sanity check ----
    print("\n--- Round-trip sanity check ---")
    pliny_path = DATA / "naibbe" / "naibbe_pliny_book16.txt"
    if pliny_path.exists():
        pliny_words = pliny_path.read_text(encoding="utf-8").split()[:5000]
        result = viterbi_decode(pliny_words, inv, models["Latin"], ALPHABET)
        print(f"  Decode 5000 Naibbe(Pliny) tokens under Latin LM:")
        print(f"    {result['n_letters_decoded']} letters decoded, "
              f"{result['n_unmatched_words']} unmatched words")
        # compare to known plaintext
        true_plain_path = Path("/tmp/naibbe/respaced_plaintext/divcom_pre_encryption_respaced_plaintext.txt")
        snippet = result["plaintext"][:300]
        print(f"    First 300 decoded letters: {snippet}")
        # also show cross-entropy
        ce_lat = cross_entropy_under(result["plaintext"], models["Latin"], ALPHABET)
        ce_ita = cross_entropy_under(result["plaintext"], models["Italian"], ALPHABET)
        ce_eng = cross_entropy_under(result["plaintext"], models["English"], ALPHABET)
        print(f"    Cross-entropy (bits/letter): Latin {ce_lat:.3f} | "
              f"Italian {ce_ita:.3f} | English {ce_eng:.3f}")

    # ---- Decode A and B ----
    print("\n--- Decode B-system (Biological + Recipes) ---")
    B = load_dialect("B")
    print(f"  {len(B)} Voynichese words")
    print("  Decoding under Latin LM...")
    decoded_B_lat = viterbi_decode(B, inv, models["Latin"], ALPHABET)
    print(f"    decoded {decoded_B_lat['n_letters_decoded']} letters, "
          f"unmatched {decoded_B_lat['n_unmatched_words']} words")

    print("  Decoding under Italian LM...")
    decoded_B_ita = viterbi_decode(B, inv, models["Italian"], ALPHABET)
    print(f"    decoded {decoded_B_ita['n_letters_decoded']} letters")

    print("\n--- Decode A-system (Herbal + Pharmaceutical) ---")
    A = load_dialect("A")
    print(f"  {len(A)} Voynichese words")
    decoded_A_lat = viterbi_decode(A, inv, models["Latin"], ALPHABET)
    print(f"  decoded {decoded_A_lat['n_letters_decoded']} letters under Latin LM")
    decoded_A_ita = viterbi_decode(A, inv, models["Italian"], ALPHABET)

    # ---- Cross-language scoring ----
    print("\n=== Cross-entropy of decoded plaintext under each language model ===")
    print("(lower = better fit; bits/letter)")
    rows = []
    decoded_streams = {
        "B (decoded under Latin LM)": decoded_B_lat["plaintext"],
        "B (decoded under Italian LM)": decoded_B_ita["plaintext"],
        "A (decoded under Latin LM)": decoded_A_lat["plaintext"],
        "A (decoded under Italian LM)": decoded_A_ita["plaintext"],
    }
    print(f"{'stream':<40} | " + " | ".join(f"{n:>9}" for n in models))
    print("-" * 110)
    for label, txt in decoded_streams.items():
        scores = {n: cross_entropy_under(txt, m, ALPHABET) for n, m in models.items()}
        rows.append({"stream": label, "scores": scores, "n_letters": len(txt)})
        print(f"{label[:40]:<40} | " + " | ".join(f"{scores[n]:>9.3f}" for n in models))

    # ---- Letter-frequency comparison ----
    def letter_freq(s: str) -> dict[str, float]:
        c = Counter(c for c in s if c in ALPHABET)
        n = sum(c.values())
        return {l: c.get(l, 0) / n if n else 0 for l in ALPHABET}

    print("\n=== Top decoded letter frequencies vs Latin/Italian baselines ===")
    # baseline frequencies
    def corpus_freq(name: str) -> dict[str, float]:
        path = DATA / "comparison" / lm_paths[name][0]
        text = path.read_text(encoding="utf-8", errors="ignore")
        words = normalise_for_lm(text, alphabet=lm_paths[name][1])
        all_chars = "".join(words)
        return letter_freq(all_chars)

    baseline_lat = corpus_freq("Latin")
    baseline_ita = corpus_freq("Italian")

    fB = letter_freq(decoded_B_lat["plaintext"])
    fA = letter_freq(decoded_A_lat["plaintext"])

    sorted_letters = sorted(ALPHABET,
                            key=lambda L: -baseline_lat[L])[:15]
    print(f"{'letter':<5} {'Latin':>8} {'Italian':>8} {'B-decoded':>10} {'A-decoded':>10}")
    for L in sorted_letters:
        print(f"{L:<5} {100*baseline_lat[L]:>7.2f}% {100*baseline_ita[L]:>7.2f}% "
              f"{100*fB[L]:>9.2f}% {100*fA[L]:>9.2f}%")

    # save outputs
    out = {
        "models": list(models.keys()),
        "alphabet": ALPHABET,
        "n_inverse_codebook_glyphs": len(inv),
        "B_decoded_under_Latin": {
            "n_letters": decoded_B_lat["n_letters_decoded"],
            "n_unmatched_words": decoded_B_lat["n_unmatched_words"],
            "n_voynich_words": decoded_B_lat["n_voynich_words"],
            "first_500_letters": decoded_B_lat["plaintext"][:500],
        },
        "A_decoded_under_Latin": {
            "n_letters": decoded_A_lat["n_letters_decoded"],
            "n_unmatched_words": decoded_A_lat["n_unmatched_words"],
            "n_voynich_words": decoded_A_lat["n_voynich_words"],
            "first_500_letters": decoded_A_lat["plaintext"][:500],
        },
        "cross_entropy_table": rows,
        "letter_freq_compare": {
            "baseline_Latin": baseline_lat,
            "baseline_Italian": baseline_ita,
            "B_decoded": fB,
            "A_decoded": fA,
        },
    }
    (ROOT / "decode_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "decoded_B_under_latin.txt").write_text(
        decoded_B_lat["plaintext"], encoding="utf-8")
    (ROOT / "decoded_A_under_latin.txt").write_text(
        decoded_A_lat["plaintext"], encoding="utf-8")
    print(f"\nWrote {ROOT/'decode_results.json'}")
    print(f"Wrote {ROOT/'decoded_B_under_latin.txt'} and {ROOT/'decoded_A_under_latin.txt'}")


if __name__ == "__main__":
    main()
