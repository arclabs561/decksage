#!/usr/bin/env python3
"""
exp_031: PageRank-based Similarity (Real Implementation)

Since metadata parsing is broken, use graph structure itself.
PageRank finds important nodes - use it as a signal.

Hypothesis: Important cards (high PageRank) are better similarity anchors.
"""

from collections import defaultdict

import numpy as np
import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def compute_pagerank(adj, iterations=20, damping=0.85):
    """Simple PageRank implementation"""
    nodes = list(adj.keys())
    n = len(nodes)
    node_to_idx = {node: i for i, node in enumerate(nodes)}

    # Initialize
    pr = np.ones(n) / n

    for _ in range(iterations):
        new_pr = np.ones(n) * (1 - damping) / n

        for node, neighbors in adj.items():
            if not neighbors:
                continue
            idx = node_to_idx[node]
            contribution = pr[idx] / len(neighbors)

            for neighbor in neighbors:
                neighbor_idx = node_to_idx[neighbor]
                new_pr[neighbor_idx] += damping * contribution

        pr = new_pr

    return {node: pr[node_to_idx[node]] for node in nodes}


def evaluate_pagerank_similarity(test_set, config):
    """Use PageRank scores to weight Jaccard"""

    df = pd.read_csv("../backend/pairs_large.csv")

    # Build graph (filter lands)
    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Command Tower", "Arid Mesa"}

    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    print(f"  Graph: {len(adj):,} cards")

    # Compute PageRank
    print("  Computing PageRank...")
    pr_scores = compute_pagerank(adj)

    top_pr = sorted(pr_scores.items(), key=lambda x: x[1], reverse=True)[:10]
    print(f"  Top PageRank cards: {[c for c, _ in top_pr]}")

    # Evaluate
    scores = []

    for query, labels in test_set.items():
        if query not in adj:
            continue

        neighbors = adj[query]
        sims = []

        # PageRank-weighted Jaccard
        for other in list(adj.keys())[:3000]:
            if other == query:
                continue

            other_n = adj[other]
            intersection = len(neighbors & other_n)
            union = len(neighbors | other_n)

            if union > 0:
                jaccard = intersection / union
                # Weight by PageRank of candidate
                pr_weight = pr_scores.get(other, 0) * 100  # Scale
                weighted_sim = jaccard * (1 + pr_weight)
                sims.append((other, weighted_sim))

        sims.sort(key=lambda x: x[1], reverse=True)

        # Score top-10
        score = 0.0
        for card, _ in sims[:10]:
            if card in labels.get("highly_relevant", []):
                score += 1.0
            elif card in labels.get("relevant", []):
                score += 0.75
            elif card in labels.get("somewhat_relevant", []):
                score += 0.5

        scores.append(score / 10.0)

    p10 = sum(scores) / len(scores) if scores else 0.0

    print(f"  P@10: {p10:.4f} on {len(scores)} queries")

    return {"p10": p10, "num_queries": len(scores), "method": "PageRank-weighted Jaccard"}


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_031",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "graph_algorithms",
        "hypothesis": "PageRank weighting improves similarity quality",
        "method": "Jaccard weighted by PageRank centrality",
        "data": "39K decks, 729K pairs",
        "uses_metadata": False,
        "note": "Works with available data (pairs.csv), no parsing needed",
    }

    results = loop.run_with_context(evaluate_pagerank_similarity, exp_config)

    print("\nREAL EXPERIMENT COMPLETE")
    print(f"  P@10: {results['p10']:.4f}")
    print("  Baseline: 0.14")
    print(f"  Change: {results['p10'] - 0.14:+.4f}")


if __name__ == "__main__":
    main()
