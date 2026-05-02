"""Word-family (edit-distance-1) analysis of Voynichese vs natural languages.

Pipeline:
  1. Tokenise every word into a glyph sequence (cTh, Sh, etc. as single units)
  2. Build an undirected graph where two words are linked iff their tokenised
     edit distance is exactly 1 (insertion / deletion / substitution at the
     glyph level)
  3. Compute connected components ("word families") and per-component stats
  4. For the top families, learn the slot grammar (which positions vary, with
     what alternants)
  5. Repeat (1)-(3) on Latin and Finnish reference corpora and compare graph
     statistics — clustering coefficient, largest-component share, degree,
     family-size distribution

Outputs:
  - voynich_families.json   (top 30 components and their slot summaries)
  - graph_stats.csv         (cross-language comparison)
  - findings_morphology.md (auto-included summary block)
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"

sys.path.insert(0, str(ROOT))
from analyze import parse_eva, tokenise_glyphs  # noqa: E402


# ----------------------------- generic graph utils ---------------------------

def deletion_set(tokens: tuple[str, ...]) -> list[tuple[str, ...]]:
    """All length-1 deletions of a token sequence."""
    return [tokens[:i] + tokens[i + 1:] for i in range(len(tokens))]


def build_ed1_graph(tokenised: list[tuple[str, ...]]) -> dict[int, set[int]]:
    """Two indices are linked iff their token sequences are at glyph edit
    distance exactly 1.

    Method (linear-ish): two strings have ed <= 1 iff they share a common
    1-deletion. We bucket by deletions and connect within buckets, then
    filter to ed == 1 (i.e. not ed == 0; we already de-duplicated).
    """
    # Bucket indices by every length-1 deletion of their token sequence
    buckets: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for idx, tokens in enumerate(tokenised):
        # Same-length neighbours: substitution at position i creates two
        # words sharing the deletion at that position. Different-length
        # neighbours: a length-(n+1) word and length-n word share a deletion
        # iff the latter is the former minus one glyph. So bucketing by
        # deletions catches both cases.
        seen_in_word: set[tuple[str, ...]] = set()
        for d in deletion_set(tokens):
            if d in seen_in_word:
                continue
            seen_in_word.add(d)
            buckets[d].append(idx)
        # also bucket the word itself (length n+1 of length-n word will share
        # the length-n word as one of its deletions; the length-n word as
        # itself does not need a special key since identical strings collapse
        # via dedup at the input level)

    # Within each bucket, every pair is at ed <= 1; ed == 0 is impossible
    # because we de-duplicated input. So every linked pair is at ed exactly 1.
    adj: dict[int, set[int]] = defaultdict(set)
    for idxs in buckets.values():
        if len(idxs) < 2:
            continue
        # A bucket can be huge for short common words (degenerate case); cap
        # by skipping mega-buckets that would create dense cliques. In
        # practice for token-level Voynichese this rarely fires.
        if len(idxs) > 1000:
            continue
        for i in range(len(idxs)):
            a = idxs[i]
            for j in range(i + 1, len(idxs)):
                b = idxs[j]
                adj[a].add(b)
                adj[b].add(a)
    return adj


def connected_components(adj: dict[int, set[int]], n_nodes: int) -> list[list[int]]:
    seen = [False] * n_nodes
    comps = []
    for start in range(n_nodes):
        if seen[start]:
            continue
        stack = [start]
        comp = []
        while stack:
            u = stack.pop()
            if seen[u]:
                continue
            seen[u] = True
            comp.append(u)
            for v in adj.get(u, ()):
                if not seen[v]:
                    stack.append(v)
        comps.append(comp)
    return comps


def local_clustering(adj: dict[int, set[int]], nodes: list[int]) -> float:
    """Average local clustering coefficient over given nodes (skip deg < 2)."""
    cs = []
    for u in nodes:
        nbrs = adj.get(u, set())
        k = len(nbrs)
        if k < 2:
            continue
        nbr_list = list(nbrs)
        links = 0
        for i in range(k):
            for j in range(i + 1, k):
                if nbr_list[j] in adj.get(nbr_list[i], ()):
                    links += 1
        cs.append(2 * links / (k * (k - 1)))
    return sum(cs) / len(cs) if cs else 0.0


def graph_stats(adj: dict[int, set[int]], n_nodes: int, label: str) -> dict:
    comps = connected_components(adj, n_nodes)
    sizes = sorted((len(c) for c in comps), reverse=True)
    n_edges = sum(len(v) for v in adj.values()) // 2
    degrees = [len(adj.get(u, ())) for u in range(n_nodes)]
    avg_deg = sum(degrees) / n_nodes if n_nodes else 0
    isolates = sum(1 for d in degrees if d == 0)
    # local clustering: sample to keep it cheap
    sample = list(range(n_nodes))
    if n_nodes > 2000:
        step = n_nodes // 2000
        sample = sample[::step]
    cc = local_clustering(adj, sample)
    return {
        "label": label,
        "n_types": n_nodes,
        "n_edges": n_edges,
        "avg_degree": avg_deg,
        "isolated_fraction": isolates / n_nodes if n_nodes else 0,
        "n_components": len(comps),
        "largest_component_size": sizes[0] if sizes else 0,
        "largest_component_share": sizes[0] / n_nodes if n_nodes else 0,
        "top10_component_sizes": sizes[:10],
        "size_geq_5_components": sum(1 for s in sizes if s >= 5),
        "size_geq_10_components": sum(1 for s in sizes if s >= 10),
        "avg_clustering_coef": cc,
    }


# --------------------------- Voynichese specific ----------------------------

def voynich_word_types(min_count: int = 2) -> tuple[list[str], list[tuple[str, ...]], Counter]:
    """Return word strings, their glyph tuples, and frequencies.

    Filters out hapax legomena by default (min_count=2) so we look at lexical
    backbone, not noise from misreadings or one-offs.
    """
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    counts: Counter = Counter()
    for r in records:
        for w in r["words"]:
            # drop uncertainty markers for graph; same as analyze.py
            counts[w] += 1
    # keep words with count >= min_count and tokenisable to len >= 2
    items = []
    for w, c in counts.items():
        if c < min_count:
            continue
        toks = tuple(tokenise_glyphs(w))
        # drop noise: pure-uncertain tokens or very short
        if len(toks) < 2 or len(toks) > 20:
            continue
        if any(t in {"*", "!"} for t in toks):
            continue
        items.append((w, toks, c))
    words = [w for w, _, _ in items]
    tokens = [t for _, t, _ in items]
    freqs = Counter({w: c for w, _, c in items})
    return words, tokens, freqs


def slot_summary(words: list[str], tokens: list[tuple[str, ...]],
                 freqs: Counter, members: list[int],
                 max_show: int = 12) -> dict:
    """Find positions where members agree and where they vary.

    Strategy: align by length (only members of modal length); for each glyph
    position list the multiset of glyphs across members, weighted by freq.
    """
    if not members:
        return {}
    lens = Counter(len(tokens[i]) for i in members)
    modal_len, _ = lens.most_common(1)[0]
    aligned = [tokens[i] for i in members if len(tokens[i]) == modal_len]
    if not aligned:
        return {}
    weights = [freqs[words[i]] for i in members if len(tokens[i]) == modal_len]
    slot_counts = []
    for pos in range(modal_len):
        c: Counter = Counter()
        for tks, w in zip(aligned, weights):
            c[tks[pos]] += w
        slot_counts.append(c.most_common())
    member_view = sorted(
        ((words[i], freqs[words[i]]) for i in members),
        key=lambda x: -x[1],
    )[:max_show]
    return {
        "modal_length": modal_len,
        "n_aligned": len(aligned),
        "slots": [
            {
                "pos": pos,
                "alternants": [(g, n) for g, n in cs],
                "is_invariant": len(cs) == 1,
            }
            for pos, cs in enumerate(slot_counts)
        ],
        "members_top": member_view,
    }


# ------------------------- comparison corpus loading ------------------------

def normalise_natural(text: str, alphabet: str = "latin") -> list[str]:
    """Lowercase, strip diacritics, keep only alphabetic words."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    if alphabet == "latin":
        toks = re.findall(r"[a-z]+", text)
    else:
        # keep latin-extended alphabetic
        toks = re.findall(r"[a-zåäöø]+", text)
    return [t for t in toks if 2 <= len(t) <= 20]


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# ------------------------------- main ---------------------------------------

def main():
    out_dir = ROOT
    out_dir.mkdir(exist_ok=True)

    # ---- Voynichese ----
    print("=== Voynichese (Takahashi, count >= 2) ===")
    words, tokens, freqs = voynich_word_types(min_count=2)
    print(f"  {len(words)} word types")
    adj = build_ed1_graph(tokens)
    vstats = graph_stats(adj, len(words), "Voynichese (count>=2)")
    for k, v in vstats.items():
        print(f"  {k}: {v}")

    # connected components, ranked by total token frequency in the family
    comps = connected_components(adj, len(words))
    family_freq = []
    for comp in comps:
        if len(comp) < 3:
            continue
        total = sum(freqs[words[i]] for i in comp)
        family_freq.append((total, comp))
    family_freq.sort(key=lambda x: -x[0])

    top_n = 30
    families_out = []
    for total, comp in family_freq[:top_n]:
        members_sorted = sorted(comp, key=lambda i: -freqs[words[i]])
        slot = slot_summary(words, tokens, freqs, comp)
        families_out.append({
            "size": len(comp),
            "total_freq": total,
            "head_word": words[members_sorted[0]],
            "members_preview": [(words[i], freqs[words[i]]) for i in members_sorted[:15]],
            "slot_summary": slot,
        })

    with (out_dir / "voynich_families.json").open("w", encoding="utf-8") as f:
        json.dump({
            "graph_stats": vstats,
            "n_families_size_geq_3": len(family_freq),
            "families": families_out,
        }, f, indent=2, ensure_ascii=False)

    # ---- Comparison corpora ----
    print("\n=== Comparison corpora ===")
    cmp_dir = DATA / "comparison"
    cmp_results = [vstats]
    for label, alphabet, fname in [
        ("Latin (Pliny)", "latin", "latin_pliny.txt"),
        ("Finnish (Bible)", "finnish", "finnish_bible.txt"),
        ("English (Pride&Prejudice)", "latin", "english_pp_clean.txt"),
        ("Italian (Divina Commedia)", "latin", "italian_dc.txt"),
    ]:
        path = cmp_dir / fname
        if not path.exists():
            print(f"  [skip] {label}: {path} not present")
            continue
        text = load_text_file(path)
        toks = normalise_natural(text, alphabet=alphabet)
        wc = Counter(toks)
        # Match Voynichese setting: count >= 2; cap to top 9000 types so graph
        # sizes are comparable
        eligible = [(w, c) for w, c in wc.items() if c >= 2]
        eligible.sort(key=lambda x: -x[1])
        eligible = eligible[: len(words)]  # cap to Voynichese vocab size
        nl_words = [w for w, _ in eligible]
        nl_tokens = [tuple(w) for w in nl_words]  # char-level tokens
        nl_freqs = Counter({w: c for w, c in eligible})
        nadj = build_ed1_graph(nl_tokens)
        ns = graph_stats(nadj, len(nl_words), label)
        ns["corpus_total_tokens"] = len(toks)
        cmp_results.append(ns)
        print(f"  {label}: {ns['n_types']} types, "
              f"largest_share={ns['largest_component_share']:.3f}, "
              f"avg_deg={ns['avg_degree']:.2f}, "
              f"cc={ns['avg_clustering_coef']:.3f}")

    # graph stats CSV
    keys = [
        "label", "n_types", "n_edges", "avg_degree", "isolated_fraction",
        "n_components", "largest_component_size", "largest_component_share",
        "size_geq_5_components", "size_geq_10_components", "avg_clustering_coef",
    ]
    with (out_dir / "graph_stats.csv").open("w", encoding="utf-8") as f:
        f.write(",".join(keys) + "\n")
        for s in cmp_results:
            f.write(",".join(str(s.get(k, "")) for k in keys) + "\n")

    print(f"\nWrote {out_dir/'voynich_families.json'} and {out_dir/'graph_stats.csv'}")


if __name__ == "__main__":
    main()
