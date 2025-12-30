#!/usr/bin/env python3
"""
exp_040: Demonstration of Refactored Code Using Shared Utils

This is a refactored version showing how experiments should look
after extracting common patterns into utils/.

Compare with run_exp_033.py (old style) to see the improvement.
"""

from true_closed_loop import ClosedLoopExperiment
from utils import (
    build_adjacency_dict,
    evaluate_similarity,
    get_filter_set,
    jaccard_similarity,
    load_pairs,
    load_test_set,
)


def refactored_jaccard_method(test_set, config):
    """Clean Jaccard implementation using shared utilities."""

    # Load data with game-aware filtering
    df = load_pairs(dataset="large", game="magic", filter_common=True, filter_level="basic")

    print(f"  Loaded {len(df):,} pairs (filtered)")

    # Build graph - no need to duplicate filtering logic
    filter_set = get_filter_set("magic", "basic")
    adj = build_adjacency_dict(df, filter_set=filter_set)

    print(f"  Graph: {len(adj):,} cards")

    # Define similarity function
    def similarity_func(query: str, k: int):
        if query not in adj:
            return []

        query_neighbors = adj[query]
        sims = []

        # Only check cards in graph
        for other in adj:
            if other == query:
                continue

            other_neighbors = adj[other]
            sim = jaccard_similarity(query_neighbors, other_neighbors)
            sims.append((other, sim))

        sims.sort(key=lambda x: x[1], reverse=True)
        return sims[:k]

    # Evaluate using standard loop
    results = evaluate_similarity(
        test_set=test_set, similarity_func=similarity_func, top_k=10, verbose=True
    )

    return results


def main():
    """Run experiment with closed-loop tracking."""

    # Load test set using shared util
    load_test_set(game="magic")

    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_040",
        "date": "2025-10-02",
        "game": "magic",
        "phase": "refactored_demonstration",
        "hypothesis": "Refactored code is cleaner and more maintainable",
        "method": "Jaccard with shared utilities",
        "improvements": [
            "No hardcoded constants",
            "Canonical path loading",
            "Reusable evaluation loop",
            "Multi-game ready",
        ],
    }

    results = loop.run_with_context(refactored_jaccard_method, exp_config)

    print(f"\n{'=' * 60}")
    print("Refactored Experiment Complete")
    print("=" * 60)
    print(f"P@10: {results['p@10']:.4f}")
    print(f"Queries: {results['num_evaluated']}/{results['num_queries']}")
    print("\nCode improvements:")
    print("  - No LANDS constant duplication")
    print("  - No hardcoded paths")
    print("  - Reusable across all games")
    print("  - Standard evaluation metrics")


if __name__ == "__main__":
    main()
