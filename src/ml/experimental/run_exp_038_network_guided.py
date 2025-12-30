#!/usr/bin/env python3
"""
exp_038: Network-Guided Experiment (A-Mem Inspired)

Source: Evolving experiment memory analyzed 35 experiments
Finding: Clustering appeared in exp_037 (successful)
Network suggests: Combine clustering signal with Jaccard

This is network-derived, not human-chosen.
"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def clustering_guided_similarity(test_set, config):
    """
    Use clustering coefficient to guide Jaccard.

    Insight from exp_037: High clustering = specialized
    Strategy: For specialized queries, boost specialized cards
    """

    df = pd.read_csv("../backend/pairs_large.csv")

    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    # Build graph
    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    # Compute clustering
    clustering = {}
    for card in adj:
        neighbors = adj[card]
        if len(neighbors) < 2:
            clustering[card] = 0
        else:
            edges_between = sum(
                1 for n1 in neighbors for n2 in neighbors if n1 < n2 and n2 in adj[n1]
            )
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            clustering[card] = edges_between / possible if possible > 0 else 0

    print(f"  Computed clustering for {len(clustering)} cards")

    # Evaluate
    scores = []

    for query, labels in test_set.items():
        if query not in adj:
            continue

        query_clust = clustering.get(query, 0)
        neighbors = adj[query]

        sims = []
        for other in list(adj.keys())[:3000]:
            if other == query or other in LANDS:
                continue

            # Jaccard
            other_n = adj[other]
            intersection = len(neighbors & other_n)
            union = len(neighbors | other_n)
            jaccard = intersection / union if union > 0 else 0

            # Clustering-based boost
            other_clust = clustering.get(other, 0)

            # If both specialized (high clustering), boost
            boost = 1.2 if query_clust > 0.3 and other_clust > 0.3 else 1.0

            combined = jaccard * boost

            sims.append((other, combined))

        sims.sort(key=lambda x: x[1], reverse=True)

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

    return {"p10": p10, "num_queries": len(scores)}


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_038",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "network_guided",
        "hypothesis": "Clustering-based boosting improves Jaccard (network suggested)",
        "method": "Jaccard with clustering-based boost",
        "data": "39K decks",
        "guided_by": "A-Mem network analysis of 35 experiments",
        "network_insight": "Clustering appeared in successful exp_037",
    }

    results = loop.run_with_context(clustering_guided_similarity, exp_config)

    print(f"\nNetwork-guided: {results['p10'] > 0.12}")

    # Update experiment memory with this result
    from evolving_experiment_memory import EvolvingExperimentMemory

    memory = EvolvingExperimentMemory()
    memory.evolve_related_memories("exp_038")
    memory.save_evolved_log()

    print("✓ Evolved related experiments with new insights")


if __name__ == "__main__":
    main()
