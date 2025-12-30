#!/usr/bin/env python3
"""
exp_028: Use Archetype Metadata (System-Directed)

System said: TRY_METADATA (P@10 too low, test set ready)
Implementation: Weight edges by archetype coherence

If Lightning Bolt appears in "Burn" archetype → high weight
If appears in random deck → low weight
"""

import json
import subprocess
from collections import defaultdict

from true_closed_loop import ClosedLoopExperiment


def train_archetype_weighted(test_set, config):
    """Build graph with archetype-weighted edges"""

    # Extract decks with archetypes
    result = subprocess.run(
        ["../backend/dataset", "cat", "magic/mtgtop8", "--bucket", "file://../backend/data-full"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Build archetype-aware graph
    archetype_pairs = defaultdict(lambda: defaultdict(int))
    card_archetypes = defaultdict(set)

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            col = data.get("collection", {})
            archetype = col.get("type", {}).get("inner", {}).get("archetype", "")

            if not archetype:
                continue

            # Get cards
            cards = []
            for partition in col.get("partitions", []):
                for card_desc in partition.get("cards", []):
                    cards.append(card_desc["name"])
                    card_archetypes[card_desc["name"]].add(archetype)

            # Co-occurrence weighted by archetype
            for i, c1 in enumerate(cards):
                for c2 in cards[i + 1 :]:
                    key = tuple(sorted([c1, c2]))
                    archetype_pairs[archetype][key] += 1
        except:
            continue

    print(f"  Archetypes found: {len(archetype_pairs)}")

    # Build weighted adjacency
    # Weight by archetype specificity:
    # - Card appears in 1 archetype → specific, high weight
    # - Card appears in many archetypes → generic, low weight

    adj_weighted = defaultdict(lambda: defaultdict(float))

    for archetype, pairs in archetype_pairs.items():
        for (c1, c2), count in pairs.items():
            # Archetype specificity
            c1_specificity = 1.0 / len(card_archetypes[c1])
            c2_specificity = 1.0 / len(card_archetypes[c2])

            # Weight by specificity and count
            weight = count * (c1_specificity + c2_specificity) / 2

            adj_weighted[c1][c2] += weight
            adj_weighted[c2][c1] += weight

    print(f"  Weighted graph: {len(adj_weighted)} cards")

    # Evaluate
    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    scores = []
    for query, labels in test_set.items():
        if query not in adj_weighted or query in LANDS:
            continue

        # Weighted similarity
        query_neighbors = adj_weighted[query]
        sims = []

        for other in list(adj_weighted.keys())[:3000]:
            if other == query or other in LANDS:
                continue

            other_neighbors = adj_weighted[other]

            # Weighted Jaccard
            intersection_weight = sum(
                min(query_neighbors.get(n, 0), other_neighbors.get(n, 0))
                for n in set(query_neighbors) & set(other_neighbors)
            )
            union_weight = sum(
                max(query_neighbors.get(n, 0), other_neighbors.get(n, 0))
                for n in set(query_neighbors) | set(other_neighbors)
            )

            if union_weight > 0:
                sims.append((other, intersection_weight / union_weight))

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

    return {
        "p10": p10,
        "num_queries": len(scores),
        "archetypes_used": len(archetype_pairs),
        "method": "Archetype-weighted Jaccard",
    }


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_028",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "metadata_usage",
        "hypothesis": "Archetype-weighted edges improve over unweighted",
        "method": "Archetype-weighted Jaccard (specificity weighting)",
        "data": "39K decks with archetype labels",
        "system_directed": True,
        "system_decision": "TRY_METADATA (from iteration 3)",
    }

    results = loop.run_with_context(train_archetype_weighted, exp_config)

    print(f"\n{'=' * 60}")
    print("exp_028: Following System Directive")
    print("=" * 60)
    print("System said: TRY_METADATA")
    print("We did: Used archetype labels")
    print(f"Result: P@10 = {results['p10']:.4f}")
    print(f"vs Baseline: {results['p10'] - 0.14:+.4f}")


if __name__ == "__main__":
    main()
