#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Extract frequent card sets from an edgelist via triangle enumeration + greedy extension.

Unlike extract_card_sets_fast.py (which needs decklists for FP-Growth), this script works
directly from a co-occurrence graph (edgelist). It finds dense card packages by:

1. Loading the weighted edgelist and filtering to high-weight edges
2. Enumerating all triangles (3-cliques) in the graph
3. Greedily extending triangles to 4- and 5-sets by adding high-weight neighbors
4. Scoring each set by a graph-based lift metric (observed vs expected density)
5. Deduplicating and outputting top-K sets as JSONL

This avoids expensive maximal clique enumeration (exponential on dense subgraphs)
by working bottom-up from triangles.

Pipeline position: Order 2.5 (alternative to extract_card_sets_fast.py for games without decklists)

Output format (JSONL):
    Line 1: {"_meta": true, ...}
    Line 2+: {"cards": ["A", "B", "C"], "support": 42, "lift": 3.7, "size": 3, ...}

Usage:
    PYTHONPATH=src python scripts/data_processing/extract_card_sets_from_graph.py \
        --edgelist data/graphs/pairs_large.edg \
        --output data/processed/card_sets_magic_top.jsonl \
        --min-weight 5 --max-size 5 --top-k 10000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


def load_edgelist(
    path: Path, min_weight: int = 2
) -> tuple[dict[str, dict[str, int]], int]:
    """Load tab-separated edgelist into adjacency dict.

    Returns (adj, edge_count) where adj[u][v] = weight.
    """
    adj: dict[str, dict[str, int]] = defaultdict(dict)
    skipped = 0
    loaded = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                skipped += 1
                continue
            card1, card2, w = parts[0], parts[1], int(parts[2])
            if w >= min_weight:
                adj[card1][card2] = w
                adj[card2][card1] = w
                loaded += 1
            else:
                skipped += 1
    print(f"  Loaded {loaded} edges, skipped {skipped} (weight < {min_weight})")
    print(f"  Graph: {len(adj)} nodes, {loaded} edges")
    return dict(adj), loaded


def enumerate_triangles(
    adj: dict[str, dict[str, int]],
) -> list[tuple[str, str, str, float]]:
    """Enumerate all triangles, return (a, b, c, total_weight) sorted by weight desc."""
    # Use node ordering to avoid duplicates: only enumerate where a < b < c
    nodes = sorted(adj.keys())
    node_idx = {n: i for i, n in enumerate(nodes)}

    triangles = []
    for u in nodes:
        neighbors_u = adj[u]
        for v in neighbors_u:
            if node_idx[v] <= node_idx[u]:
                continue
            neighbors_v = adj[v]
            # Find common neighbors w > v
            for w in neighbors_u:
                if node_idx[w] <= node_idx[v]:
                    continue
                if w in neighbors_v:
                    total_w = neighbors_u[v] + neighbors_u[w] + neighbors_v[w]
                    triangles.append((u, v, w, total_w))

    triangles.sort(key=lambda x: -x[3])
    return triangles


def score_set(adj: dict[str, dict[str, int]], cards: frozenset[str]) -> tuple[float, int]:
    """Return (total_weight, edge_count) for internal edges of a card set."""
    card_list = list(cards)
    n = len(card_list)
    total_weight = 0.0
    edge_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            w = adj.get(card_list[i], {}).get(card_list[j], 0)
            if w > 0:
                total_weight += w
                edge_count += 1
    return total_weight, edge_count


def extend_set(
    adj: dict[str, dict[str, int]],
    base: frozenset[str],
    max_size: int,
    node_strengths: dict[str, float],
    total_strength: float,
) -> list[tuple[frozenset[str], float, float, float]]:
    """Greedily extend a base set by adding neighbors connected to all members.

    Returns list of (card_set, total_weight, density, lift) for the base and extensions.
    """
    results = []
    base_tw, base_ec = score_set(adj, base)
    n = len(base)
    max_edges = n * (n - 1) / 2
    density = base_tw / max_edges if max_edges > 0 else 0
    lift = compute_lift(base, base_tw, node_strengths, total_strength)
    results.append((base, base_tw, density, lift))

    if len(base) >= max_size:
        return results

    # Find candidates: nodes connected to ALL members of base
    base_list = list(base)
    candidates: dict[str, float] = {}
    # Start from neighbors of the first member, then intersect
    first_neighbors = set(adj.get(base_list[0], {}).keys())
    common = first_neighbors - base
    for member in base_list[1:]:
        member_neighbors = set(adj.get(member, {}).keys())
        common &= member_neighbors

    for candidate in common:
        # Sum of weights to all base members
        total_w_to_base = sum(adj[candidate].get(m, 0) for m in base_list)
        candidates[candidate] = total_w_to_base

    # Sort candidates by total weight to base (descending)
    sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])

    # Greedily add top candidates
    current = base
    for cand, _ in sorted_candidates[:5]:  # try top 5 candidates
        extended = current | {cand}
        if len(extended) > max_size:
            break
        ext_tw, ext_ec = score_set(adj, extended)
        ext_n = len(extended)
        ext_max_edges = ext_n * (ext_n - 1) / 2
        ext_density = ext_tw / ext_max_edges if ext_max_edges > 0 else 0
        ext_lift = compute_lift(extended, ext_tw, node_strengths, total_strength)
        results.append((extended, ext_tw, ext_density, ext_lift))

        # Also try extending further from this point
        if len(extended) < max_size:
            current_ext = extended
            ext_list = list(current_ext)
            # Find common neighbors of extended set
            ext_common = set(adj.get(ext_list[0], {}).keys()) - current_ext
            for m in ext_list[1:]:
                ext_common &= set(adj.get(m, {}).keys())
            for cand2_node in sorted(ext_common, key=lambda c: -sum(adj[c].get(m, 0) for m in ext_list))[:3]:
                ext2 = current_ext | {cand2_node}
                if len(ext2) > max_size:
                    break
                e2_tw, _ = score_set(adj, ext2)
                e2_n = len(ext2)
                e2_me = e2_n * (e2_n - 1) / 2
                e2_density = e2_tw / e2_me if e2_me > 0 else 0
                e2_lift = compute_lift(ext2, e2_tw, node_strengths, total_strength)
                results.append((ext2, e2_tw, e2_density, e2_lift))

    return results


def compute_lift(
    card_set: frozenset[str],
    total_weight: float,
    node_strengths: dict[str, float],
    total_strength: float,
) -> float:
    """Lift = observed avg edge weight / expected avg edge weight under independence."""
    n = len(card_set)
    max_edges = n * (n - 1) / 2
    if max_edges == 0 or total_strength == 0:
        return 0.0

    observed = total_weight / max_edges

    cards = list(card_set)
    expected = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            si = node_strengths.get(cards[i], 0)
            sj = node_strengths.get(cards[j], 0)
            expected += (si * sj) / total_strength
    expected /= max_edges

    if expected == 0:
        return float("inf")
    return observed / expected


def main():
    parser = argparse.ArgumentParser(
        description="Extract card sets from edgelist via triangle enumeration"
    )
    parser.add_argument("--edgelist", type=Path, required=True, help="Tab-separated edgelist file")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL file")
    parser.add_argument(
        "--min-weight", type=int, default=5,
        help="Minimum edge weight to include (default: 5)",
    )
    parser.add_argument(
        "--min-size", type=int, default=3,
        help="Minimum set size (default: 3)",
    )
    parser.add_argument(
        "--max-size", type=int, default=5,
        help="Maximum set size (default: 5)",
    )
    parser.add_argument(
        "--top-k", type=int, default=10_000,
        help="Keep top K sets by score (default: 10000)",
    )
    parser.add_argument(
        "--max-triangles", type=int, default=500_000,
        help="Max triangles to process for extension (default: 500000)",
    )
    parser.add_argument("--game", type=str, default="magic", help="Game name for metadata")
    args = parser.parse_args()

    if not args.edgelist.exists():
        print(f"Error: edgelist not found: {args.edgelist}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()

    # Step 1: Load graph
    print(f"Loading edgelist from {args.edgelist}...")
    adj, edge_count = load_edgelist(args.edgelist, min_weight=args.min_weight)

    if len(adj) < args.min_size:
        print("Error: graph too small", file=sys.stderr)
        sys.exit(1)

    # Precompute node strengths for lift
    node_strengths: dict[str, float] = defaultdict(float)
    for u, neighbors in adj.items():
        for v, w in neighbors.items():
            node_strengths[u] += w
    # Each edge counted from both sides, so divide total by 2
    total_strength = sum(node_strengths.values()) / 2

    # Step 2: Enumerate triangles
    print("Enumerating triangles...")
    t1 = time.time()
    triangles = enumerate_triangles(adj)
    print(f"  Found {len(triangles)} triangles in {time.time() - t1:.1f}s")

    if not triangles:
        print("No triangles found. Try lowering --min-weight.", file=sys.stderr)
        sys.exit(1)

    # Show weight distribution of triangles
    tri_weights = [t[3] for t in triangles]
    print(f"  Triangle weight range: {min(tri_weights)}-{max(tri_weights)}, "
          f"median={tri_weights[len(tri_weights)//2]}")

    # Step 3: Extend top triangles to larger sets
    process_count = min(len(triangles), args.max_triangles)
    print(f"Extending top {process_count} triangles to size {args.min_size}-{args.max_size}...")
    t2 = time.time()

    all_sets: dict[frozenset[str], tuple[float, float, float]] = {}  # -> (total_weight, density, lift)

    for idx, (a, b, c, tw) in enumerate(triangles[:process_count]):
        base = frozenset({a, b, c})
        extensions = extend_set(adj, base, args.max_size, node_strengths, total_strength)

        for card_set, total_w, density, lift in extensions:
            if len(card_set) < args.min_size:
                continue
            existing = all_sets.get(card_set)
            if existing is None or total_w > existing[0]:
                all_sets[card_set] = (total_w, density, lift)

        if (idx + 1) % 100_000 == 0:
            print(f"    Processed {idx + 1}/{process_count} triangles, "
                  f"{len(all_sets)} unique sets")

    print(f"  {len(all_sets)} unique sets in {time.time() - t2:.1f}s")

    # Step 4: Rank and select top-K
    scored = []
    for card_set, (total_w, density, lift) in all_sets.items():
        size = len(card_set)
        score = size * density * lift
        scored.append({
            "cards": sorted(card_set),
            "size": size,
            "support": round(total_w),
            "support_pct": 0.0,
            "lift": round(lift, 3),
            "density": round(density, 3),
            "total_weight": round(total_w),
            "score": round(score, 3),
        })

    scored.sort(key=lambda x: (-x["score"], -x["size"], -x["lift"]))
    results = scored[: args.top_k]

    # Filter to size >= min_size (should already be, but defensive)
    results = [r for r in results if r["size"] >= args.min_size]

    elapsed = time.time() - t0

    # Step 5: Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        meta = {
            "_meta": True,
            "game": args.game,
            "source": str(args.edgelist),
            "method": "triangle_enumeration+greedy_extension",
            "min_weight": args.min_weight,
            "min_size": args.min_size,
            "max_size": args.max_size,
            "total_nodes": len(adj),
            "total_edges": edge_count,
            "total_triangles": len(triangles),
            "total_sets_found": len(all_sets),
            "total_sets_output": len(results),
            "elapsed_seconds": round(elapsed, 1),
        }
        f.write(json.dumps(meta) + "\n")
        for item in results:
            f.write(json.dumps(item) + "\n")

    # Summary
    by_size = defaultdict(list)
    for r in results:
        by_size[r["size"]].append(r)

    print(f"\nResults ({elapsed:.1f}s):")
    print(f"  Total sets output: {len(results)} (of {len(all_sets)} found)")
    for size in sorted(by_size):
        items = by_size[size]
        avg_lift = sum(i["lift"] for i in items) / len(items) if items else 0
        avg_density = sum(i["density"] for i in items) / len(items) if items else 0
        print(f"  {size}-card sets: {len(items)} (avg lift: {avg_lift:.2f}, avg density: {avg_density:.1f})")

    for size in sorted(by_size):
        items = sorted(by_size[size], key=lambda x: -x["lift"])[:5]
        print(f"\n  Top {size}-card sets by lift:")
        for item in items:
            cards = ", ".join(item["cards"])
            print(f"    lift={item['lift']:.2f}  weight={item['total_weight']}  "
                  f"density={item['density']:.1f}  [{cards}]")

    print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
