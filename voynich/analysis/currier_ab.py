"""Currier A/B dialect comparison.

Phase 1 confirmed two empirical clusters by glyph-distribution JSD:
  A-cluster: Herbal + Pharmaceutical  (JSD 0.015 — most similar pair)
  B-cluster: Biological + Recipes      (JSD 0.016)

We test whether A and B are:
  H1. Same codebook, different plaintext (vocab broadly shared, frequencies
      differ)
  H2. Different codebook (vocab largely disjoint beyond chance)
  H3. Same codebook + same language plus rendering tweaks

Tests:
  1. Vocabulary overlap |V_A ∩ V_B| / |V_A ∪ V_B|. Compare to chance baseline
     under random equal-size sampling from a shared pool.
  2. Frequency-distribution JSD between A and B word distributions.
  3. Top-50 words of A and B: shared vs disjoint.
  4. Per-dialect word families (ed=1 graph). Are the two structures the
     same? Compare graph_avg_degree, largest_component_share, etc.
  5. For the top family in each dialect, look at its slot grammar — same
     positions, same alternants, same probabilities?
  6. Naibbe-specific test: Naibbe tables include unigram words for each
     plaintext letter. Are A's and B's most-frequent short words plausibly
     the same Naibbe-table outputs?

Outputs:
  currier_ab_results.json
  currier_ab_summary.csv
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))
from analyze import parse_eva, tokenise_glyphs  # noqa: E402
from word_families import build_ed1_graph, graph_stats, connected_components  # noqa: E402


# Currier-style section assignment. We use the Phase-1 empirical split.
SECTION_TO_DIALECT = {
    "Herbal": "A",
    "Pharmaceutical": "A",
    "Biological": "B",
    "Recipes": "B",
    "Cosmological": "B-",      # closer to B but not committed
    "Astronomical": "A-",     # ambiguous
    "Unknown": None,
}


def load_dialect_corpora():
    records = parse_eva(DATA / "voynich_eva.txt")
    records = [r for r in records if r["src"] == "H"]
    A = []  # tokens
    B = []
    for r in records:
        d = SECTION_TO_DIALECT.get(r["section"])
        if d not in ("A", "B"):
            continue
        for w in r["words"]:
            if not w or any(c in "*!" for c in w):
                continue
            (A if d == "A" else B).append(w)
    return A, B


def js_divergence(p: dict, q: dict, keys=None) -> float:
    if keys is None:
        keys = set(p) | set(q)
    sp, sq = sum(p.values()), sum(q.values())
    pp = np.array([p.get(k, 0) / sp for k in keys])
    qq = np.array([q.get(k, 0) / sq for k in keys])
    mm = 0.5 * (pp + qq)
    def kl(a, b):
        mask = (a > 0) & (b > 0)
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))
    return 0.5 * kl(pp, mm) + 0.5 * kl(qq, mm)


def hyper_expected_overlap(N_a: int, N_b: int, N_pool: int) -> float:
    """Expected |V_a ∩ V_b| if both are equal-size random samples without
    replacement from a shared pool of size N_pool. Used as a chance
    baseline.

    Uses indicator-trick: for a single type, P(in V_a) = 1 - C(N_pool-1, N_a)/C(N_pool, N_a)
    ≈ 1 - (1 - N_a/N_pool) for large N_pool. So P(in both) ≈ (N_a/N_pool)*(N_b/N_pool).

    Then expected overlap ≈ N_pool * (N_a/N_pool) * (N_b/N_pool) = N_a*N_b/N_pool.
    This is sufficient as a rough comparison.
    """
    if N_pool == 0:
        return 0.0
    return N_a * N_b / N_pool


def per_dialect_families(words):
    counts = Counter(words)
    types = []
    type_tokens = []
    for w, c in counts.items():
        if c < 2:
            continue
        toks = tuple(tokenise_glyphs(w))
        if len(toks) < 2 or len(toks) > 20:
            continue
        if any(t in {"*", "!"} for t in toks):
            continue
        types.append(w)
        type_tokens.append(toks)
    adj = build_ed1_graph(type_tokens)
    gs = graph_stats(adj, len(types), "subset")
    comps = connected_components(adj, len(types))
    sizes = sorted((len(c) for c in comps), reverse=True)
    # build family list
    fams = []
    for comp in comps:
        if len(comp) < 3:
            continue
        total = sum(counts[types[i]] for i in comp)
        head = sorted(comp, key=lambda i: -counts[types[i]])[0]
        fams.append({
            "size": len(comp),
            "total_freq": total,
            "head_word": types[head],
            "members": sorted(comp, key=lambda i: -counts[types[i]]),
            "members_words": [types[i] for i in sorted(comp, key=lambda i: -counts[types[i]])][:30],
            "type_indices": comp,
        })
    fams.sort(key=lambda f: -f["total_freq"])
    return {
        "graph_stats": gs,
        "n_families_geq_3": len(fams),
        "n_families_geq_10": sum(1 for f in fams if f["size"] >= 10),
        "top_families": fams[:10],
        "top_size_dist": sizes[:20],
        "types": types,
        "type_tokens": type_tokens,
        "counts": counts,
    }


def slot_grammar(words: list[str], type_indices: list[int],
                 type_tokens: list[tuple[str, ...]],
                 counts: Counter, types: list[str]) -> dict:
    """Slot summary for the modal-length subset of a family."""
    if not type_indices:
        return {}
    lens = Counter(len(type_tokens[i]) for i in type_indices)
    modal_len, _ = lens.most_common(1)[0]
    aligned = [type_tokens[i] for i in type_indices if len(type_tokens[i]) == modal_len]
    weights = [counts[types[i]] for i in type_indices if len(type_tokens[i]) == modal_len]
    if not aligned:
        return {}
    slot_counts = []
    for pos in range(modal_len):
        c: Counter = Counter()
        for tks, w in zip(aligned, weights):
            c[tks[pos]] += w
        slot_counts.append(c.most_common())
    return {
        "modal_length": modal_len,
        "n_aligned_types": len(aligned),
        "slots": [
            {"pos": p, "alternants": [(g, n) for g, n in s[:8]],
             "is_invariant": len(s) == 1}
            for p, s in enumerate(slot_counts)
        ],
    }


def main():
    print("Loading A/B subcorpora...")
    A, B = load_dialect_corpora()
    cA, cB = Counter(A), Counter(B)
    print(f"  A: {len(A)} tokens, {len(cA)} types  (Herbal+Pharmaceutical)")
    print(f"  B: {len(B)} tokens, {len(cB)} types  (Biological+Recipes)")

    # ----- 1) vocabulary overlap -----
    types_A = set(cA)
    types_B = set(cB)
    inter = types_A & types_B
    union = types_A | types_B
    jacc = len(inter) / len(union)
    chance_overlap_estimate = hyper_expected_overlap(
        len(types_A), len(types_B), len(union)
    )
    overlap_ratio = len(inter) / chance_overlap_estimate \
        if chance_overlap_estimate else float("nan")

    # token-mass overlap: fraction of A's tokens in shared vocabulary
    tokens_in_shared_A = sum(c for w, c in cA.items() if w in inter)
    tokens_in_shared_B = sum(c for w, c in cB.items() if w in inter)

    print("\n=== Vocabulary overlap ===")
    print(f"  |V_A| = {len(types_A)}   |V_B| = {len(types_B)}")
    print(f"  |V_A ∩ V_B| = {len(inter)} ({100*jacc:.1f}% Jaccard)")
    print(f"  Chance overlap estimate: {chance_overlap_estimate:.0f}")
    print(f"  Observed/chance ratio: {overlap_ratio:.2f}")
    print(f"  A tokens in shared vocab: {100*tokens_in_shared_A/len(A):.1f}%")
    print(f"  B tokens in shared vocab: {100*tokens_in_shared_B/len(B):.1f}%")

    # ----- 2) frequency-distribution JSD -----
    fdist_jsd = js_divergence(cA, cB)
    # also restrict to top-1000 most common
    top1k = set([w for w, _ in (cA + cB).most_common(1000)])
    fdist_jsd_top = js_divergence({w: cA.get(w, 0) for w in top1k},
                                   {w: cB.get(w, 0) for w in top1k},
                                   keys=top1k)
    print(f"\n=== Frequency-distribution JSD ===")
    print(f"  Full vocabulary: JSD(A,B) = {fdist_jsd:.4f}")
    print(f"  Top-1000 vocabulary: JSD(A,B) = {fdist_jsd_top:.4f}")

    # ----- 3) top words of each -----
    print("\n=== Top 15 words: A vs B ===")
    print(f"{'rank':<5} {'A word':<14} {'A count':>8} {'B count':>8}  | {'B word':<14} {'B count':>8} {'A count':>8}")
    for i, ((wa, ca), (wb, cb)) in enumerate(zip(cA.most_common(15), cB.most_common(15))):
        print(f"{i+1:<5} {wa:<14} {ca:>8} {cB.get(wa, 0):>8}  | {wb:<14} {cb:>8} {cA.get(wb, 0):>8}")

    # ----- 4) per-dialect families -----
    print("\n=== Per-dialect word-family graphs ===")
    famA = per_dialect_families(A)
    famB = per_dialect_families(B)
    print(f"{'metric':<26} {'A':>14} {'B':>14}")
    for k in ["n_types", "n_edges", "avg_degree", "largest_component_share",
              "avg_clustering_coef"]:
        print(f"{k:<26} {famA['graph_stats'][k]:>14.4f} {famB['graph_stats'][k]:>14.4f}")
    print(f"{'n_families_geq_3':<26} {famA['n_families_geq_3']:>14} {famB['n_families_geq_3']:>14}")
    print(f"{'n_families_geq_10':<26} {famA['n_families_geq_10']:>14} {famB['n_families_geq_10']:>14}")

    # ----- 5) head words of top families -----
    print("\n=== Top family head words ===")
    print(f"{'rank':<5} {'A head':<14} {'A size':>7} {'A freq':>7}  | {'B head':<14} {'B size':>7} {'B freq':>7}")
    for i in range(min(8, len(famA["top_families"]), len(famB["top_families"]))):
        a, b = famA["top_families"][i], famB["top_families"][i]
        print(f"{i+1:<5} {a['head_word']:<14} {a['size']:>7} {a['total_freq']:>7}  | "
              f"{b['head_word']:<14} {b['size']:>7} {b['total_freq']:>7}")

    # ----- 6) slot grammar of top family for each -----
    print("\n=== Slot grammar of TOP family in A vs B ===")
    for label, fam_data in [("A", famA), ("B", famB)]:
        if not fam_data["top_families"]:
            continue
        f = fam_data["top_families"][0]
        sg = slot_grammar([], f["type_indices"], fam_data["type_tokens"],
                          fam_data["counts"], fam_data["types"])
        print(f"  Dialect {label}: head={f['head_word']}, size={f['size']}, "
              f"modal_len={sg.get('modal_length')}")
        for slot in sg.get("slots", []):
            top4 = [(g, n) for g, n in slot["alternants"][:4]]
            print(f"    pos {slot['pos']}: {top4}")
        print()

    # ----- 6.5) Naibbe-table probe: decode top words of A and B against
    #            the Naibbe codebook to see which plaintext letters and
    #            which tables they would correspond to.
    print("\n=== Naibbe-codebook probe: which plaintext letters dominate? ===")
    naibbe_csv = DATA / "naibbe" / "naibbe_tables.csv"
    glyph_to_codes: dict[str, list[str]] = defaultdict(list)
    if naibbe_csv.exists():
        with naibbe_csv.open(encoding="utf-8-sig") as f:
            for line in f.readlines()[1:]:
                code, gly = line.strip().split(",", 1)
                glyph_to_codes[gly].append(code)

        def probe(top_words):
            letter_score: Counter = Counter()
            table_score: Counter = Counter()
            state_score: Counter = Counter()
            ambig = 0
            unmatched = 0
            total_freq = 0
            for w, n in top_words:
                total_freq += n
                # try EVA-lowercase form (Naibbe stores lowercase)
                key = w.replace("Sh", "sh").replace("cTh", "cth") \
                       .replace("cKh", "ckh").replace("cPh", "cph") \
                       .replace("cFh", "cfh")
                cands = glyph_to_codes.get(key, [])
                if not cands:
                    unmatched += n
                    continue
                if len(cands) > 1:
                    ambig += n
                # weighted vote across all candidates
                for c in cands:
                    state, table, letter = c.split("_", 2)
                    letter_score[letter] += n / len(cands)
                    table_score[table] += n / len(cands)
                    state_score[state] += n / len(cands)
            return letter_score, table_score, state_score, unmatched, total_freq

        for label, c in [("A", cA), ("B", cB)]:
            top200 = c.most_common(200)
            ls, ts, ss, unm, tot = probe(top200)
            print(f"\n  Dialect {label} (top-200 words, {tot} tokens):")
            print(f"    Unmatched (not in Naibbe codebook): {100*unm/tot:.1f}%")
            print(f"    Letter distribution (top 12):")
            for L, sc in ls.most_common(12):
                print(f"      {L}: {100*sc/tot:.2f}%")
            print(f"    Table preference:")
            for T, sc in ts.most_common():
                print(f"      {T}: {100*sc/tot:.2f}%")
            print(f"    State (unigram vs prefix vs suffix):")
            for S, sc in ss.most_common():
                print(f"      {S}: {100*sc/tot:.2f}%")

    # ----- 7) save -----
    summary = {
        "n_tokens_A": len(A), "n_tokens_B": len(B),
        "n_types_A": len(cA), "n_types_B": len(cB),
        "intersection_size": len(inter),
        "union_size": len(union),
        "jaccard": jacc,
        "chance_overlap_estimate": chance_overlap_estimate,
        "observed_over_chance_ratio": overlap_ratio,
        "frac_A_tokens_in_shared_vocab": tokens_in_shared_A / len(A),
        "frac_B_tokens_in_shared_vocab": tokens_in_shared_B / len(B),
        "fdist_jsd_full": fdist_jsd,
        "fdist_jsd_top1000": fdist_jsd_top,
        "graph_A": famA["graph_stats"],
        "graph_B": famB["graph_stats"],
        "top_words_A": cA.most_common(20),
        "top_words_B": cB.most_common(20),
        "top_families_A_heads": [(f["head_word"], f["size"], f["total_freq"])
                                 for f in famA["top_families"][:10]],
        "top_families_B_heads": [(f["head_word"], f["size"], f["total_freq"])
                                 for f in famB["top_families"][:10]],
    }

    # Slot grammar of each top family
    for label, fam_data in [("A", famA), ("B", famB)]:
        if fam_data["top_families"]:
            f = fam_data["top_families"][0]
            sg = slot_grammar([], f["type_indices"], fam_data["type_tokens"],
                              fam_data["counts"], fam_data["types"])
            summary[f"top_family_{label}_head"] = f["head_word"]
            summary[f"top_family_{label}_slots"] = sg

    (ROOT / "currier_ab_results.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"\nWrote {ROOT/'currier_ab_results.json'}")


if __name__ == "__main__":
    main()
