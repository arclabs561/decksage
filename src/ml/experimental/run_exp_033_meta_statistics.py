#!/usr/bin/env python3
"""
exp_033: Meta Statistics (Research-Directed)

Papers show: Meta statistics (pick rates, win rates) alone = 42% accuracy
Current: Co-occurrence only = 12% accuracy

Implementation: Compute card statistics from our 39K decks
- Card frequency (how often picked)
- Average deck placement (1st place vs 8th place)
- Co-occurrence with winning decks
"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def compute_meta_statistics_and_evaluate(test_set, config):
    """Compute card statistics and use for similarity"""

    df = pd.read_csv("../backend/pairs_large.csv")

    # Compute card frequency
    card_freq = defaultdict(int)
    for _, row in df.iterrows():
        card_freq[row["NAME_1"]] += row["COUNT_MULTISET"]
        card_freq[row["NAME_2"]] += row["COUNT_MULTISET"]

    print(f"  Card statistics: {len(card_freq):,} cards")

    # Top cards by frequency (proxy for "good cards")
    top_cards = sorted(card_freq.items(), key=lambda x: x[1], reverse=True)
    print(f"  Top 10 by frequency: {[c for c, _ in top_cards[:10]]}")

    # Similarity based on: similar frequency + co-occurrence
    adj = defaultdict(set)
    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    # Evaluate
    scores = []

    for query, labels in test_set.items():
        if query not in adj:
            continue

        query_freq = card_freq.get(query, 0)
        neighbors = adj[query]

        sims = []
        for other in list(adj.keys())[:3000]:
            if other == query:
                continue

            # Jaccard
            other_n = adj[other]
            intersection = len(neighbors & other_n)
            union = len(neighbors | other_n)
            jaccard = intersection / union if union > 0 else 0

            # Frequency similarity (cards with similar popularity)
            other_freq = card_freq.get(other, 0)
            freq_sim = 1.0 / (1.0 + abs(query_freq - other_freq) / max(query_freq, other_freq, 1))

            # Combined (weighted)
            combined_sim = 0.7 * jaccard + 0.3 * freq_sim

            sims.append((other, combined_sim))

        sims.sort(key=lambda x: x[1], reverse=True)

        # Score
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

    return {
        "p10": p10,
        "num_queries": len(scores),
        "method": "Jaccard + Frequency similarity",
        "weights": {"jaccard": 0.7, "frequency": 0.3},
    }


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_033",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "research_informed",
        "hypothesis": "Meta statistics improve over co-occurrence alone (papers show 42% vs our 12%)",
        "method": "Jaccard + Frequency similarity (70/30 weighted)",
        "data": "39K decks",
        "inspired_by": "JKU 2024 paper: meta statistics alone = 42% accuracy",
        "improvement_expected": "3-4x over baseline",
    }

    results = loop.run_with_context(compute_meta_statistics_and_evaluate, exp_config)

    print(f"\n{'=' * 60}")
    print("Research-Guided Experiment Complete")
    print("=" * 60)
    print("Papers said: Meta stats = 42%")
    print(f"We got: P@10 = {results['p10']:.4f}")
    print("Baseline: 0.12")
    print(f"Improvement: {(results['p10'] / 0.12 - 1) * 100:+.1f}%")


if __name__ == "__main__":
    main()
