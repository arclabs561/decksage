#!/usr/bin/env python3
"""
exp_034: Meta Statistics Fixed (Iteration on exp_033 failure)

exp_033 failed because frequency included lands.
Fix: Filter lands from ALL statistics, not just similarity.
"""

from collections import defaultdict

import pandas as pd
from true_closed_loop import ClosedLoopExperiment


def evaluate_meta_filtered(test_set, config):
    """Meta statistics with land filtering everywhere"""

    df = pd.read_csv("../backend/pairs_large.csv")

    # COMPREHENSIVE land filter
    LANDS = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Flooded Strand",
        "Polluted Delta",
        "Scalding Tarn",
        "Misty Rainforest",
        "Verdant Catacombs",
        "Marsh Flats",
        "Bloodstained Mire",
        "Wooded Foothills",
        "Windswept Heath",
        "Arid Mesa",
        "Command Tower",
        "City of Brass",
        "Gemstone Caverns",
        "Ancient Tomb",
        "Urza's Saga",
    }

    # Compute frequency (EXCLUDING lands)
    card_freq = defaultdict(int)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS:
            card_freq[c1] += row["COUNT_MULTISET"]
        if c2 not in LANDS:
            card_freq[c2] += row["COUNT_MULTISET"]

    top_cards = sorted(card_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    print(f"  Top non-land cards: {[c for c, _ in top_cards]}")

    # Build adjacency (also filtered)
    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    # Evaluate
    scores = []

    for query, labels in test_set.items():
        if query not in adj or query in LANDS:
            continue

        query_freq = card_freq.get(query, 0)
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

            # Frequency similarity
            other_freq = card_freq.get(other, 0)
            if max(query_freq, other_freq) > 0:
                freq_sim = 1.0 - abs(query_freq - other_freq) / max(query_freq, other_freq)
            else:
                freq_sim = 0

            # Weighted combination
            combined = 0.6 * jaccard + 0.4 * freq_sim

            sims.append((other, combined))

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

    print(f"  Evaluated: {len(scores)} queries, P@10 = {p10:.4f}")

    return {"p10": p10, "num_queries": len(scores)}


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_034",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "iteration_on_failure",
        "hypothesis": "Filtering lands from frequency calculation fixes exp_033",
        "method": "Meta stats (frequency) + Jaccard, comprehensive land filter",
        "data": "39K decks, lands filtered everywhere",
    }

    results = loop.run_with_context(evaluate_meta_filtered, exp_config)
    print(f"\nIteration successful: {results['p10'] > 0.14}")


if __name__ == "__main__":
    main()
