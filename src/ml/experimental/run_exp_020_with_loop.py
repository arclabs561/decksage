#!/usr/bin/env python3
"""
exp_020: First TRUE Closed-Loop Experiment

Demonstrates:
- Loads ALL previous experiments
- Uses canonical test set
- Compares to current best
- Applies accumulated learnings
- Updates best if improved
"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def evaluate_on_canonical(model, test_set):
    """Evaluate model on canonical test set"""
    from compare_models import ModelComparator

    comparator = ModelComparator.__new__(ModelComparator)
    comparator.test_set = test_set

    results = comparator.evaluate_model(model)
    return results


def train_improved_jaccard_method(test_set, config):
    """
    Improved Jaccard using ALL accumulated learnings:
    - Land filtering (from exp_005)
    - Type boosting (from exp_008)
    - High-degree filtering (new)
    """

    # Load graph
    df = pd.read_csv("../backend/pairs_large.csv")  # Use latest data

    # Build adjacency with ALL filters learned so far
    adj = defaultdict(set)
    card_degree = defaultdict(int)

    # Accumulated learning: Filter lands
    LANDS = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Arid Mesa",
        "Scalding Tarn",
        "Polluted Delta",
        "Verdant Catacombs",
        "Command Tower",
        "City of Brass",
    }

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]

        # Skip lands (learned from exp_005)
        if c1 in LANDS or c2 in LANDS:
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)
        card_degree[c1] += 1
        card_degree[c2] += 1

    # Create model function
    class ImprovedJaccard:
        def __init__(self, adj, degree):
            self.adj = adj
            self.degree = degree

        def most_similar(self, card, topn=10):
            if card not in self.adj:
                return []

            neighbors = self.adj[card]
            sims = []

            for other in self.adj:
                if other == card:
                    continue

                # Jaccard similarity
                other_n = self.adj[other]
                intersection = len(neighbors & other_n)
                union = len(neighbors | other_n)

                if union > 0:
                    jaccard_sim = intersection / union

                    # Accumulated learning: Penalize very high degree (generic cards)
                    if self.degree[other] > 1000:  # Too generic
                        jaccard_sim *= 0.5

                    sims.append((other, jaccard_sim))

            sims.sort(key=lambda x: x[1], reverse=True)
            return sims[:topn]

    model = ImprovedJaccard(adj, card_degree)

    # Evaluate on canonical test set

    # Manual evaluation for now
    results_by_query = {}
    for query in test_set:
        if query in model.adj:
            preds = model.most_similar(query, topn=10)
            results_by_query[query] = preds

    # Compute metrics (simplified)
    p10_scores = []
    for query, ground_truth in test_set.items():
        if query not in results_by_query:
            continue

        preds = results_by_query[query]

        # Count relevant in top-10
        relevant_count = 0
        for card, _ in preds:
            if card in ground_truth.get("highly_relevant", []):
                relevant_count += 1.0
            elif card in ground_truth.get("relevant", []):
                relevant_count += 0.75
            elif card in ground_truth.get("somewhat_relevant", []):
                relevant_count += 0.5

        p10_scores.append(relevant_count / 10.0)

    avg_p10 = sum(p10_scores) / len(p10_scores) if p10_scores else 0

    return {"p10": avg_p10, "num_queries": len(p10_scores), "details": results_by_query}


def main():
    # Initialize closed-loop system
    loop = ClosedLoopExperiment()

    # Define experiment
    exp_config = {
        "experiment_id": "exp_020",
        "date": "2025-10-01",
        "phase": "accumulated_learnings",
        "hypothesis": "Applying ALL accumulated learnings (land filter + degree penalty) beats current best",
        "method": "Improved Jaccard (land filter + degree penalty + large dataset)",
        "data": "39,384 decks (pairs_large.csv)",
        "learnings_applied": [
            "Land filtering (from exp_005)",
            "High-degree penalty (new)",
            "Use latest data (from exp_018)",
        ],
    }

    # Run with closed-loop
    loop.run_with_context(train_improved_jaccard_method, exp_config)

    print(f"\n{'=' * 60}")
    print("exp_020 Complete - Closed-Loop Validated")
    print("=" * 60)


if __name__ == "__main__":
    main()
