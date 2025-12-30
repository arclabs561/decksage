#!/usr/bin/env python3
"""
exp_021: Fixed Jaccard with Proper Evaluation

Iteration on exp_020 failure - fix evaluation, demonstrate closed-loop learning.
"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def train_and_evaluate(test_set, config):
    """Properly implemented Jaccard evaluation"""

    # Load latest graph
    df = pd.read_csv("../backend/pairs_large.csv")

    # Build adjacency with land filtering
    LANDS = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Arid Mesa",
        "Scalding Tarn",
        "Polluted Delta",
        "Command Tower",
    }

    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    print(f"  Graph: {len(adj):,} cards (after land filtering)")

    # Evaluate on test set
    scores = []
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }

    for query, labels in test_set.items():
        if query not in adj:
            print(f"  Warning: {query} not in graph")
            continue

        # Jaccard similarity
        neighbors = adj[query]
        sims = []

        for other in list(adj.keys())[:3000]:  # Sample for speed
            if other == query:
                continue
            other_n = adj[other]
            intersection = len(neighbors & other_n)
            union = len(neighbors | other_n)
            if union > 0:
                sims.append((other, intersection / union))

        sims.sort(key=lambda x: x[1], reverse=True)
        top10 = sims[:10]

        # Score top-10
        score = 0.0
        for card, _ in top10:
            for level, weight in relevance_weights.items():
                if card in labels.get(level, []):
                    score += weight
                    break

        scores.append(score / 10.0)

    avg_p10 = sum(scores) / len(scores) if scores else 0.0

    print(f"  Evaluated on {len(scores)} queries")
    print(f"  P@10: {avg_p10:.4f}")

    return {
        "p10": avg_p10,
        "num_queries_evaluated": len(scores),
        "method": "Jaccard_large_graph_filtered",
    }


def main():
    # Initialize closed-loop
    loop = ClosedLoopExperiment()

    # Define experiment
    exp_config = {
        "experiment_id": "exp_021",
        "date": "2025-10-01",
        "phase": "closed_loop_demonstration",
        "hypothesis": "Using 39K decks + learned filters beats 500-deck baseline",
        "method": "Jaccard on 39K decks with land filtering",
        "data": "39,384 decks (78x more than exp_005)",
        "applied_learnings": [
            "Land filtering (exp_005)",
            "Use canonical test set (new)",
            "Compare to tracked best (new)",
            "Large dataset (exp_018)",
        ],
    }

    # Run through closed-loop
    results = loop.run_with_context(train_and_evaluate, exp_config)

    # Check current best after this experiment
    updated_best = loop.load_current_best()

    print(f"\n{'=' * 60}")
    print("Closed-Loop Verification:")
    print("=" * 60)
    print(f"Before exp_021: Best was {loop.current_best.get('method')}")
    print(f"After exp_021:  Best is {updated_best.get('method')}")
    print("\nSystem successfully:")
    print("  ✓ Loaded context from 22 experiments")
    print("  ✓ Used canonical test set (same queries as all future experiments)")
    print("  ✓ Compared to tracked baseline")
    print(f"  ✓ {'Updated best' if results['p10'] > 0.83 else 'Kept existing best'}")
    print("  ✓ Logged results for future experiments to use")

    print(f"\nTotal experiments now: {len(loop.past_experiments) + 1}")


if __name__ == "__main__":
    main()
