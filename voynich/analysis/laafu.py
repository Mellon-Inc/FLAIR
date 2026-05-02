"""LAAFU — Line As A Functional Unit.

Test whether Voynichese word distribution depends on position within a line.
If the text is "real" left-to-right writing, no positional bias should exist
beyond what punctuation/sentence-boundary effects produce in natural text.

We compute, separately for each section (Currier-style):

1. Glyph distribution at word position 0 (line-first), 1 (line-second),
   -1 (line-last), -2 (line-penultimate), and "medial" (everything else).
2. Word-length distribution at the same positions.
3. JSD between (line-first vs medial), (line-last vs medial), etc.
4. The same metrics for English (Pride and Prejudice) and Latin (Pliny) as
   controls — but split into "lines" of comparable length so the comparison
   is meaningful.

Strong LAAFU effect = JSD between line-edge and line-medial is much larger
in Voynichese than in natural-language controls. That would be evidence
that Voynichese line structure is doing something non-textual (e.g. lines
are "verses" of the generative system, with different slot rules).

Outputs:
  laafu.json   — full per-section, per-position summary + JSDs
  laafu.csv    — flat table of JSDs per (corpus, position)
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"

sys.path.insert(0, str(ROOT))
from analyze import parse_eva, tokenise_glyphs, section_for  # noqa: E402


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


def position_buckets(words: list[str]) -> dict[str, list[str]]:
    """Return five buckets of words from a single line."""
    n = len(words)
    if n == 0:
        return {}
    out = {"first": [], "second": [], "last": [], "penult": [], "medial": []}
    for i, w in enumerate(words):
        if i == 0:
            out["first"].append(w)
        elif i == 1 and n > 1:
            out["second"].append(w)
        if i == n - 1 and n > 1:
            out["last"].append(w)
        elif i == n - 2 and n > 2:
            out["penult"].append(w)
        if 1 < i < n - 2:
            out["medial"].append(w)
    return out


def glyph_dist(words: list[str]) -> Counter:
    c: Counter = Counter()
    for w in words:
        for g in tokenise_glyphs(w):
            c[g] += 1
    return c


def length_dist(words: list[str]) -> Counter:
    c: Counter = Counter()
    for w in words:
        L = len(tokenise_glyphs(w))
        if L > 0:
            c[L] += 1
    return c


def voynich_buckets():
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    sect_buckets: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {k: [] for k in ["first", "second", "last", "penult", "medial"]}
    )
    for r in records:
        words = [w for w in r["words"] if w and not all(c in "*!" for c in w)]
        bs = position_buckets(words)
        for k, v in bs.items():
            sect_buckets[r["section"]][k].extend(v)
            sect_buckets["ALL"][k].extend(v)
    return sect_buckets


def natural_buckets(path: Path, alphabet: str = "latin"):
    """Treat each non-empty line of source text as one 'line' (split on
    newline). Apply same positional bucketing.

    For prose collapse very long paragraphs; we split on sentence end so
    that line lengths are comparable to Voynich (median ~7 words/line).
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    # split on sentence-ending punctuation to get pseudo-lines
    pseudo_lines = re.split(r"(?<=[.!?:])\s+|\n+", text)
    if alphabet == "finnish":
        word_re = re.compile(r"[a-zåäöø]+", re.IGNORECASE)
    else:
        word_re = re.compile(r"[a-z]+", re.IGNORECASE)
    bs = {k: [] for k in ["first", "second", "last", "penult", "medial"]}
    for line in pseudo_lines:
        words = [w.lower() for w in word_re.findall(line)]
        if 2 <= len(words) <= 25:
            for k, v in position_buckets(words).items():
                bs[k].extend(v)
    return bs


def _glyph_for_natural(words: list[str]) -> Counter:
    """For natural-language strings just count chars."""
    c: Counter = Counter()
    for w in words:
        for g in w:
            c[g] += 1
    return c


def jsd_table(buckets: dict[str, list[str]], glyph_fn) -> dict[str, float]:
    """JSD vs medial baseline for each non-medial bucket."""
    medial = glyph_fn(buckets.get("medial", []))
    out = {}
    for k in ["first", "second", "last", "penult"]:
        if buckets.get(k):
            out[k] = js_divergence(glyph_fn(buckets[k]), medial)
        else:
            out[k] = float("nan")
    return out


def length_jsd(buckets):
    medial = length_dist(buckets.get("medial", []))
    out = {}
    for k in ["first", "second", "last", "penult"]:
        out[k] = js_divergence(length_dist(buckets.get(k, [])), medial) \
            if buckets.get(k) else float("nan")
    return out


def main():
    out_dir = ROOT
    print("=== Voynichese: LAAFU per section (vs medial) ===")
    voy = voynich_buckets()
    voynich_results = {}
    print(f"{'section':<15} {'pos':<8} {'glyph_JSD':>10} {'len_JSD':>10} {'n':>6}")
    for sect, b in voy.items():
        glyph_jsd = jsd_table(b, glyph_dist)
        len_jsd = length_jsd(b)
        for k in ["first", "second", "last", "penult"]:
            n = len(b.get(k, []))
            print(f"{sect:<15} {k:<8} {glyph_jsd.get(k, float('nan')):>10.4f} "
                  f"{len_jsd.get(k, float('nan')):>10.4f} {n:>6}")
        voynich_results[sect] = {
            "glyph_jsd": glyph_jsd,
            "length_jsd": len_jsd,
            "counts": {k: len(b.get(k, [])) for k in b},
        }

    print("\n=== Natural-language controls (sentence-split as 'lines') ===")
    nat = {}
    nat_paths = [
        ("Latin (Pliny)", "latin", "latin_pliny.txt"),
        ("Italian (Dante)", "latin", "italian_dc.txt"),
        ("Finnish (Bible)", "finnish", "finnish_bible.txt"),
        ("English (P&P)", "latin", "english_pp_clean.txt"),
    ]
    print(f"{'corpus':<22} {'pos':<8} {'char_JSD':>10} {'len_JSD':>10} {'n':>6}")
    for label, alpha, fname in nat_paths:
        path = DATA / "comparison" / fname
        if not path.exists():
            continue
        bs = natural_buckets(path, alphabet=alpha)
        gj = jsd_table(bs, _glyph_for_natural)
        lj = length_jsd(bs)
        for k in ["first", "second", "last", "penult"]:
            print(f"{label:<22} {k:<8} {gj[k]:>10.4f} {lj[k]:>10.4f} {len(bs.get(k, [])):>6}")
        nat[label] = {
            "char_jsd_vs_medial": gj,
            "length_jsd_vs_medial": lj,
            "counts": {k: len(bs.get(k, [])) for k in bs},
        }

    # Flat CSV summary
    csv_lines = ["corpus,position,glyph_or_char_jsd,length_jsd,n_words"]
    for sect, d in voynich_results.items():
        for k in ["first", "second", "last", "penult"]:
            csv_lines.append(
                f"voynich:{sect},{k},{d['glyph_jsd'].get(k, float('nan')):.6f},"
                f"{d['length_jsd'].get(k, float('nan')):.6f},{d['counts'].get(k, 0)}"
            )
    for label, d in nat.items():
        for k in ["first", "second", "last", "penult"]:
            csv_lines.append(
                f"{label},{k},{d['char_jsd_vs_medial'][k]:.6f},"
                f"{d['length_jsd_vs_medial'][k]:.6f},{d['counts'].get(k, 0)}"
            )
    (out_dir / "laafu.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    with (out_dir / "laafu.json").open("w", encoding="utf-8") as f:
        json.dump({"voynich": voynich_results, "natural_controls": nat},
                  f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_dir/'laafu.csv'} and {out_dir/'laafu.json'}")


if __name__ == "__main__":
    main()
