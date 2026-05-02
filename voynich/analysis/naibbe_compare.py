"""Compare Naibbe-cipher output against real Voynichese.

Naibbe (Greshko 2025) is a verbose homophonic substitution cipher proposed
as a "historically plausible" generator of Voynichese-like text. We use the
reference implementation's pre-encrypted outputs:

  data/naibbe/naibbe_pliny_book16.txt    Pliny Nat. Hist. Book XVI -> Naibbe
  data/naibbe/naibbe_divcom.txt          Divina Commedia (Italian)  -> Naibbe

We compute on each: token count, type count, hapax ratio, mean word length,
glyph h1/h2, Zipf slope, repetition rate, edit-distance graph statistics.
We compare to:

  - Real Voynichese (Takahashi)
  - Phase-4 best slot-grammar null model (M3) for context

Strong test: if Naibbe matches real Voynichese on the metrics where the
slot null model failed (h2, type count, Zipf, repetition rate), then the
verbose-substitution-cipher hypothesis gains substantial empirical support.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva, tokenise_glyphs  # noqa: E402
from word_families import build_ed1_graph, graph_stats  # noqa: E402


def load_real():
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    return [w for r in records for w in r["words"]
            if w and not any(c in "*!" for c in w)]


def load_naibbe(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    # split on whitespace; preserve word boundaries already encoded in spaces
    return [w.strip() for w in text.split() if w.strip()]


def shannon(c: Counter) -> float:
    n = sum(c.values())
    return -sum((v/n) * math.log2(v/n) for v in c.values() if v > 0) if n else 0.0


def conditional_entropy(stream: list[str]) -> tuple[float, float]:
    n = len(stream)
    if n < 3:
        return (0.0, 0.0)
    c1 = Counter(stream)
    h1 = shannon(c1)
    bg = Counter(zip(stream[:-1], stream[1:]))
    prev = Counter(stream[:-1])
    h2 = 0.0
    for (a, b), c in bg.items():
        pab = c / (n - 1)
        pa = prev[a] / (n - 1)
        if pab > 0 and pa > 0:
            h2 -= pab * math.log2(pab / pa)
    return (h1, h2)


def zipf_fit(c: Counter) -> tuple[float, float]:
    freqs = sorted(c.values(), reverse=True)
    if len(freqs) < 5:
        return (float("nan"), float("nan"))
    ranks = np.arange(1, len(freqs) + 1)
    x = np.log10(ranks); y = np.log10(np.array(freqs))
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return (float(slope), 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"))


def repetition(words: list[str]) -> float:
    n = rep = 0
    for a, b in zip(words[:-1], words[1:]):
        n += 1
        if a == b:
            rep += 1
    return rep / n if n else 0.0


def positional_glyphs(words: list[str]) -> dict[str, dict[str, float]]:
    init: Counter = Counter(); med: Counter = Counter(); fin: Counter = Counter()
    for w in words:
        toks = tokenise_glyphs(w)
        if not toks:
            continue
        if len(toks) == 1:
            init[toks[0]] += 1
            fin[toks[0]] += 1
            continue
        init[toks[0]] += 1
        fin[toks[-1]] += 1
        for t in toks[1:-1]:
            med[t] += 1
    out = {}
    for g in set(init) | set(med) | set(fin):
        T = init.get(g, 0) + med.get(g, 0) + fin.get(g, 0)
        if T < 100:
            continue
        out[g] = {
            "total": T,
            "initial": init.get(g, 0) / T,
            "medial": med.get(g, 0) / T,
            "final": fin.get(g, 0) / T,
        }
    return out


def section_glyph_jsd(_records, label):  # not used here
    return {}


def corpus_summary(words: list[str], label: str) -> dict:
    word_counts = Counter(words)
    glyph_stream = []
    for w in words:
        glyph_stream.extend(tokenise_glyphs(w))
    h1, h2 = conditional_entropy(glyph_stream)
    z, r2 = zipf_fit(word_counts)
    n = sum(word_counts.values())
    avg_wlen = sum(len(tokenise_glyphs(w)) * c for w, c in word_counts.items()) / n if n else 0
    types = [w for w, c in word_counts.items() if c >= 2]
    type_tokens = [tuple(tokenise_glyphs(w)) for w in types
                   if 2 <= len(tokenise_glyphs(w)) <= 20
                   and not any(t in {"*", "!"} for t in tokenise_glyphs(w))]
    type_kept = [w for w in types
                 if 2 <= len(tokenise_glyphs(w)) <= 20
                 and not any(t in {"*", "!"} for t in tokenise_glyphs(w))]
    adj = build_ed1_graph(type_tokens)
    gs = graph_stats(adj, len(type_kept), label)
    hapax = sum(1 for c in word_counts.values() if c == 1)

    pos = positional_glyphs(words)
    # signature glyphs: q (initial?), n (final?), i (medial?)
    sig = {
        g: {
            "total": d["total"],
            "initial": round(d["initial"], 3),
            "medial": round(d["medial"], 3),
            "final": round(d["final"], 3),
        }
        for g, d in pos.items() if g in {"q", "n", "i", "y", "ch", "Sh", "k", "t"}
    }

    return {
        "label": label,
        "n_tokens": n,
        "n_types": len(word_counts),
        "type_token_ratio": len(word_counts) / n if n else 0,
        "hapax_ratio": hapax / len(word_counts) if word_counts else 0,
        "avg_word_length": avg_wlen,
        "h1_unigram": h1,
        "h2_conditional": h2,
        "zipf_slope": z,
        "zipf_r2": r2,
        "repetition_rate": repetition(words),
        "graph_n_types_used": gs["n_types"],
        "graph_avg_degree": gs["avg_degree"],
        "graph_largest_share": gs["largest_component_share"],
        "graph_clustering": gs["avg_clustering_coef"],
        "graph_components_geq_10": gs["size_geq_10_components"],
        "positional_signature": sig,
    }


def main():
    print("Loading real Voynichese...")
    real = load_real()
    real_summary = corpus_summary(real, "Real Voynichese")

    print(f"  {real_summary['n_tokens']} tokens, {real_summary['n_types']} types")

    print("\nLoading Naibbe(Pliny)...")
    pliny_naibbe = load_naibbe(DATA / "naibbe" / "naibbe_pliny_book16.txt")
    pliny_naibbe_summary = corpus_summary(pliny_naibbe, "Naibbe(Pliny BookXVI)")

    print("Loading Naibbe(Divina Commedia)...")
    dc_naibbe = load_naibbe(DATA / "naibbe" / "naibbe_divcom.txt")
    dc_naibbe_summary = corpus_summary(dc_naibbe, "Naibbe(Divina Commedia)")

    # Truncate Naibbe corpora to real-token-count for fair comparison
    print("\nMaking length-matched Naibbe samples (n_tokens = real)...")
    n_real = real_summary["n_tokens"]
    rng_seed_offset = 0  # deterministic by construction (head slice)
    pliny_match = corpus_summary(pliny_naibbe[:n_real], "Naibbe(Pliny) matched")
    dc_match = corpus_summary(dc_naibbe[:n_real], "Naibbe(Dante) matched")

    results = [real_summary, pliny_naibbe_summary, pliny_match,
               dc_naibbe_summary, dc_match]

    # ------- comparison table -------
    keys = [
        "label", "n_tokens", "n_types", "type_token_ratio", "hapax_ratio",
        "avg_word_length", "h1_unigram", "h2_conditional", "zipf_slope",
        "zipf_r2", "repetition_rate", "graph_n_types_used", "graph_avg_degree",
        "graph_largest_share", "graph_clustering", "graph_components_geq_10"
    ]
    print("\n=== COMPARISON ===")
    print(f"{'metric':<24} | " + " | ".join(f"{r['label'][:21]:>21}" for r in results))
    print("-" * 165)
    for k in keys[1:]:
        vals = [r[k] for r in results]
        fmt = lambda v: f"{v:>21.4f}" if isinstance(v, float) else f"{v:>21}"
        print(f"{k:<24} | " + " | ".join(fmt(v) for v in vals))

    print("\n=== POSITIONAL SIGNATURE: q (initial), n (final), i (medial) ===")
    print(f"{'corpus':<22} {'glyph':<5} {'total':>6} {'initial':>8} {'medial':>8} {'final':>8}")
    for r in [real_summary, pliny_naibbe_summary, dc_naibbe_summary]:
        for g in ["q", "n", "i", "y", "ch", "Sh"]:
            d = r["positional_signature"].get(g)
            if d is None:
                continue
            print(f"{r['label'][:22]:<22} {g:<5} {d['total']:>6} "
                  f"{d['initial']:>8.3f} {d['medial']:>8.3f} {d['final']:>8.3f}")
        print()

    # ---- write outputs ----
    out = {"results": results}
    (ROOT / "naibbe_comparison.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_lines = [",".join(keys)]
    for r in results:
        csv_lines.append(",".join(str(r[k]) if k != "positional_signature" else ""
                                  for k in keys))
    (ROOT / "naibbe_comparison.csv").write_text(
        "\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {ROOT/'naibbe_comparison.json'} and {ROOT/'naibbe_comparison.csv'}")


if __name__ == "__main__":
    main()
