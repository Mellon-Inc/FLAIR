"""Voynich Manuscript statistical analysis.

Reads the Takahashi EVA transliteration (IVTFF-style locators) and computes:
- Glyph (character) frequencies, including capitalised-EVA digraphs
- Word frequencies, length distribution, hapax ratio
- Zipf-law fit (exponent and R^2)
- Shannon entropy h0, h1, h2 on glyph stream
- Per-section breakdown (Currier-style section by folio range) with vocabulary
  overlap and JSD on glyph distributions
- Word-position glyph statistics (which glyphs prefer word-initial / final / medial)

Outputs CSVs and a markdown summary into voynich/analysis/.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
OUT = ROOT

LOCATOR_RE = re.compile(r"^<(?P<folio>f[0-9]+[rv][0-9]*)\.(?P<unit>[^.;]+)\.(?P<line>[0-9]+);(?P<src>[A-Z])>\s*(?P<text>.*)$")
FOLIO_NUM_RE = re.compile(r"f(\d+)([rv])")

# Currier/Stolfi-style section ranges (folio number, inclusive).
# Source: voynich.nu/descr.html and standard Voynich literature.
SECTIONS = [
    ("Herbal",         1,   66),   # f1r-f66v
    ("Astronomical",   67,  73),   # f67r-f73v (incl. Zodiac at f70v-f73v)
    ("Cosmological",   85,  86),   # foldouts (Q14)
    ("Biological",     75,  84),   # "balneological", nymphs in tubs
    ("Pharmaceutical", 87,  102),  # jars, root sections
    ("Recipes",        103, 116),  # star-paragraphs (Q20)
]


def section_for(folio: str) -> str:
    m = FOLIO_NUM_RE.match(folio)
    if not m:
        return "Unknown"
    n = int(m.group(1))
    for name, lo, hi in SECTIONS:
        if lo <= n <= hi:
            return name
    return "Unknown"


def parse_eva(path: Path):
    """Parse the IVTFF-style transliteration.

    Returns list of records: {folio, unit, line, src, text_raw, words}.
    Cleans Takahashi conventions:
      - '.' is intra-line word separator
      - '-' at line end is line continuation (no word break inside files; we
        already have line-by-line text, so we just strip them)
      - '!' and '*' mark uncertain glyphs and unreadable glyphs respectively
      - '=' marks paragraph end
      - '%' page break (not in our data)
    Capitalised EVA: cTh, cKh, cPh, cFh, Sh are multi-glyph tokens.
    For glyph counting we treat them as single units.
    """
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = LOCATOR_RE.match(line)
            if not m:
                continue
            text = m.group("text")
            # strip the trailing '-' (line-cont) and '=' (paragraph end)
            text = text.rstrip("-=").strip()
            # For word splitting we use '.' separator only; '-' is structural.
            # Keep '*' and '!' as glyph tokens (uncertain markers); we'll
            # decide per-stat whether to count them.
            words = [w for w in text.split(".") if w]
            records.append({
                "folio": m.group("folio"),
                "unit": m.group("unit"),
                "line": int(m.group("line")),
                "src": m.group("src"),
                "text": text,
                "words": words,
                "section": section_for(m.group("folio")),
            })
    return records


# Capitalised-EVA multi-glyph tokens in Takahashi's convention
MULTI_GLYPHS = ["cTh", "cKh", "cPh", "cFh", "Sh", "ch", "sh", "ckh", "cph", "cfh", "cth"]
# Sort longest-first for greedy match
MULTI_GLYPHS = sorted(set(MULTI_GLYPHS), key=len, reverse=True)


def tokenise_glyphs(word: str, drop_uncertain: bool = True) -> list[str]:
    """Greedy tokeniser that respects multi-glyph capitalised EVA digraphs.

    With drop_uncertain=True, '*' and '!' are removed.
    """
    if drop_uncertain:
        word = word.replace("*", "").replace("!", "")
    tokens = []
    i = 0
    while i < len(word):
        matched = None
        for mg in MULTI_GLYPHS:
            if word.startswith(mg, i):
                matched = mg
                break
        if matched:
            tokens.append(matched)
            i += len(matched)
        else:
            tokens.append(word[i])
            i += 1
    return tokens


def glyph_stats(records):
    glyph_counts = Counter()
    glyph_stream_by_section: dict[str, list[str]] = defaultdict(list)
    for r in records:
        for w in r["words"]:
            toks = tokenise_glyphs(w)
            glyph_counts.update(toks)
            glyph_stream_by_section[r["section"]].extend(toks)
            glyph_stream_by_section["ALL"].extend(toks)
    return glyph_counts, glyph_stream_by_section


def word_stats(records):
    word_counts = Counter()
    word_len_counts = Counter()
    by_section: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for w in r["words"]:
            toks = tokenise_glyphs(w)
            if not toks:
                continue
            # canonical word string = joined tokens (so cTh treated as 1 glyph for length)
            word_counts[w] += 1
            word_len_counts[len(toks)] += 1
            by_section[r["section"]][w] += 1
    return word_counts, word_len_counts, by_section


def shannon_entropy(counts) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        if p > 0:
            h -= p * math.log2(p)
    return h


def conditional_entropy(stream: list[str]) -> tuple[float, float, float]:
    """Returns (h0, h1, h2)."""
    n = len(stream)
    if n < 3:
        return (0.0, 0.0, 0.0)
    c1 = Counter(stream)
    h0 = math.log2(len(c1))
    h1 = shannon_entropy(c1)

    # h2 = H(X_t | X_{t-1}) using bigrams
    bg = Counter(zip(stream[:-1], stream[1:]))
    # P(prev) marginal
    prev = Counter(stream[:-1])
    h2 = 0.0
    for (a, b), cab in bg.items():
        pab = cab / (n - 1)
        pa = prev[a] / (n - 1)
        if pab > 0 and pa > 0:
            h2 -= pab * math.log2(pab / pa)
    return (h0, h1, h2)


def zipf_fit(counts: Counter) -> tuple[float, float, int]:
    """Fit log(rank) -> log(freq); returns (slope, r2, n_types)."""
    freqs = sorted(counts.values(), reverse=True)
    if len(freqs) < 5:
        return (float("nan"), float("nan"), len(freqs))
    ranks = np.arange(1, len(freqs) + 1)
    x = np.log10(ranks)
    y = np.log10(np.array(freqs))
    # least squares
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return (float(slope), float(r2), len(freqs))


def js_divergence(p: Counter, q: Counter) -> float:
    keys = set(p) | set(q)
    sp, sq = sum(p.values()), sum(q.values())
    if sp == 0 or sq == 0:
        return float("nan")
    pp = np.array([p.get(k, 0) / sp for k in keys])
    qq = np.array([q.get(k, 0) / sq for k in keys])
    mm = 0.5 * (pp + qq)
    def kl(a, b):
        mask = (a > 0) & (b > 0)
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))
    return 0.5 * kl(pp, mm) + 0.5 * kl(qq, mm)


def positional_glyph_stats(records):
    initial = Counter()
    final = Counter()
    medial = Counter()
    for r in records:
        for w in r["words"]:
            toks = tokenise_glyphs(w)
            if not toks:
                continue
            if len(toks) == 1:
                initial[toks[0]] += 1
                final[toks[0]] += 1
                continue
            initial[toks[0]] += 1
            final[toks[-1]] += 1
            for t in toks[1:-1]:
                medial[t] += 1
    return initial, medial, final


def write_csv(path: Path, header, rows):
    with path.open("w", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(c) for c in row) + "\n")


def main():
    src = DATA / "voynich_eva.txt"
    print(f"Loading {src}")
    records = parse_eva(src)
    # restrict to Takahashi 'H' source if available; otherwise keep all
    h_records = [r for r in records if r["src"] == "H"]
    print(f"  parsed {len(records)} lines, Takahashi(H) lines: {len(h_records)}")
    records = h_records

    glyph_counts, streams = glyph_stats(records)
    word_counts, wlen_counts, sect_words = word_stats(records)

    # global metrics
    total_tokens = sum(word_counts.values())
    n_types = len(word_counts)
    hapax = sum(1 for c in word_counts.values() if c == 1)
    avg_wlen = sum(L * n for L, n in wlen_counts.items()) / sum(wlen_counts.values())
    var_wlen = sum(((L - avg_wlen) ** 2) * n for L, n in wlen_counts.items()) / sum(wlen_counts.values())

    h0_all, h1_all, h2_all = conditional_entropy(streams["ALL"])
    z_slope, z_r2, _ = zipf_fit(word_counts)

    summary = {
        "total_word_tokens": total_tokens,
        "vocabulary_size": n_types,
        "hapax_count": hapax,
        "hapax_ratio": hapax / n_types if n_types else 0,
        "type_token_ratio": n_types / total_tokens if total_tokens else 0,
        "mean_word_length_glyphs": avg_wlen,
        "std_word_length_glyphs": math.sqrt(var_wlen),
        "n_glyph_types": len(glyph_counts),
        "glyph_h0_max_uniform_bits": h0_all,
        "glyph_h1_unigram_bits": h1_all,
        "glyph_h2_conditional_bits": h2_all,
        "zipf_slope": z_slope,
        "zipf_r2": z_r2,
        "n_lines": len(records),
        "n_folios": len({r["folio"] for r in records}),
    }

    # per-section
    sect_summary = {}
    for sect in [s[0] for s in SECTIONS] + ["Unknown"]:
        if sect not in streams:
            continue
        gc = Counter(streams[sect])
        wc = sect_words[sect]
        if not wc:
            continue
        h0, h1, h2 = conditional_entropy(streams[sect])
        zs, zr2, _ = zipf_fit(wc)
        wlens = Counter(len(tokenise_glyphs(w)) for w in wc.elements())
        if sum(wlens.values()):
            mu = sum(L * n for L, n in wlens.items()) / sum(wlens.values())
        else:
            mu = 0
        sect_summary[sect] = {
            "tokens": sum(wc.values()),
            "types": len(wc),
            "hapax": sum(1 for c in wc.values() if c == 1),
            "ttr": len(wc) / sum(wc.values()) if sum(wc.values()) else 0,
            "mean_wlen": mu,
            "h1": h1,
            "h2": h2,
            "zipf_slope": zs,
            "zipf_r2": zr2,
            "n_glyphs": sum(gc.values()),
            "top_words": wc.most_common(10),
        }

    # JSD between section glyph distributions
    sect_names = [s for s in [n for n, _, _ in SECTIONS] if s in streams]
    jsd = {}
    for i, a in enumerate(sect_names):
        for b in sect_names[i + 1:]:
            jsd[f"{a}|{b}"] = js_divergence(Counter(streams[a]), Counter(streams[b]))

    # positional
    initial, medial, final = positional_glyph_stats(records)

    # ---- write outputs ----
    OUT.mkdir(exist_ok=True)
    write_csv(OUT / "glyph_freq.csv", ["glyph", "count"],
              sorted(glyph_counts.items(), key=lambda x: -x[1]))
    write_csv(OUT / "word_freq.csv", ["word", "count"],
              word_counts.most_common(500))
    write_csv(OUT / "word_length_dist.csv", ["length_glyphs", "count"],
              sorted(wlen_counts.items()))
    write_csv(OUT / "positional_glyphs.csv",
              ["glyph", "initial", "medial", "final"],
              [(g, initial.get(g, 0), medial.get(g, 0), final.get(g, 0))
               for g in sorted(set(initial) | set(medial) | set(final),
                               key=lambda x: -(initial.get(x, 0) + medial.get(x, 0) + final.get(x, 0)))])

    with (OUT / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({
            "global": summary,
            "sections": sect_summary,
            "section_glyph_jsd": jsd,
        }, f, indent=2, ensure_ascii=False)

    # console report
    def fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    print("\n=== GLOBAL ===")
    for k, v in summary.items():
        print(f"  {k}: {fmt(v)}")

    print("\n=== SECTIONS ===")
    print(f"{'section':<16} {'tokens':>8} {'types':>7} {'TTR':>6} {'wlen':>6} {'h1':>6} {'h2':>6} {'zipf':>7} {'r2':>6}")
    for s, d in sect_summary.items():
        print(f"{s:<16} {d['tokens']:>8} {d['types']:>7} {d['ttr']:>6.3f} {d['mean_wlen']:>6.2f} "
              f"{d['h1']:>6.3f} {d['h2']:>6.3f} {d['zipf_slope']:>7.3f} {d['zipf_r2']:>6.3f}")

    print("\n=== JSD between section glyph distributions (lower = more similar) ===")
    for k, v in sorted(jsd.items(), key=lambda x: x[1]):
        print(f"  {k}: {v:.4f}")

    print("\n=== TOP 15 WORDS ===")
    for w, c in word_counts.most_common(15):
        print(f"  {w:<12} {c}")

    print("\n=== TOP 10 GLYPHS ===")
    total_g = sum(glyph_counts.values())
    for g, c in glyph_counts.most_common(10):
        print(f"  {g:<5} {c:>7}  ({100*c/total_g:.2f}%)")

    print("\n=== POSITIONAL TENDENCIES (top by skew) ===")
    rows = []
    for g in initial:
        I, M, F = initial.get(g, 0), medial.get(g, 0), final.get(g, 0)
        T = I + M + F
        if T < 200:
            continue
        rows.append((g, T, I/T, M/T, F/T))
    rows.sort(key=lambda r: -r[1])
    print(f"{'glyph':<5} {'total':>7} {'initial':>8} {'medial':>8} {'final':>8}")
    for g, T, i, m, fi in rows[:15]:
        print(f"{g:<5} {T:>7} {i:>8.3f} {m:>8.3f} {fi:>8.3f}")


if __name__ == "__main__":
    main()
