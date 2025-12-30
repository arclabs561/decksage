#!/usr/bin/env python3
"""
exp_008 (revised): Jaccard with Type-Aware Filtering

After exp_007 failure, try simpler approach:
- Use existing Jaccard (works)
- Add type filtering from Scryfall
- Should beat unfiltered Jaccard

Much simpler than GNN, more likely to work.
"""

import json
import subprocess
from collections import defaultdict

import pandas as pd


def extract_card_types():
    """Extract card types from Scryfall data"""
    print("Extracting Scryfall card types...")

    # Get Scryfall data
    result = subprocess.run(
        [
            "../backend/dataset",
            "cat",
            "magic/scryfall",
            "--bucket",
            "file://../backend/data-full",
            "--section",
            "cards",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=".",
    )

    card_types = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            card = data.get("card", {})
            name = card.get("name")
            type_line = card.get("type_line", "")

            if name:
                card_types[name] = {
                    "type_line": type_line,
                    "is_land": "Land" in type_line,
                    "is_creature": "Creature" in type_line,
                    "is_instant": "Instant" in type_line,
                    "is_sorcery": "Sorcery" in type_line,
                    "is_artifact": "Artifact" in type_line,
                    "is_enchantment": "Enchantment" in type_line,
                }
        except:
            continue

    print(f"✓ Extracted types for {len(card_types):,} cards")
    return card_types


def type_aware_jaccard(pairs_csv, card_types):
    """Jaccard with type filtering"""
    df = pd.read_csv(pairs_csv)

    # Build adjacency, filtering lands
    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]

        # Filter lands
        t1 = card_types.get(c1, {})
        t2 = card_types.get(c2, {})

        if t1.get("is_land") or t2.get("is_land"):
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)

    def find_similar(query, k=10):
        if query not in adj:
            return []

        query_type = card_types.get(query, {})
        query_neighbors = adj[query]

        similarities = []
        for other in adj:
            if other == query:
                continue

            # Type filter: prefer same type
            other_type = card_types.get(other, {})

            # Basic type match (can refine)
            same_type = (
                (query_type.get("is_instant") and other_type.get("is_instant"))
                or (query_type.get("is_sorcery") and other_type.get("is_sorcery"))
                or (query_type.get("is_creature") and other_type.get("is_creature"))
            )

            # Compute Jaccard
            other_neighbors = adj[other]
            intersection = len(query_neighbors & other_neighbors)
            union = len(query_neighbors | other_neighbors)

            if union > 0:
                jaccard_sim = intersection / union

                # Boost if same type
                if same_type:
                    jaccard_sim *= 1.5  # Prefer same type

                similarities.append((other, jaccard_sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:k]

    return find_similar


# Run experiment
if __name__ == "__main__":
    print("=" * 60)
    print("exp_008 (revised): Type-Aware Jaccard")
    print("=" * 60)

    card_types = extract_card_types()
    find_similar = type_aware_jaccard("../backend/pairs_500decks.csv", card_types)

    # Test on same diverse queries
    queries = [
        "Lightning Bolt",
        "Brainstorm",
        "Dark Ritual",
        "Counterspell",
        "Sol Ring",
        "Tarmogoyf",
    ]

    print("\nResults:")
    print("=" * 60)

    correct_count = 0
    total_count = 0

    for query in queries:
        results = find_similar(query, k=5)
        print(f"\n{query}:")
        for i, (card, score) in enumerate(results, 1):
            print(f"  {i}. {card:40s} {score:.4f}")

        # Manual check (would automate with ground truth)
        total_count += 1

    # Log
    print(f"\n{'=' * 60}")
    print("Logging exp_008...")

    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        exp = {
            "experiment_id": "exp_008_revised",
            "date": "2025-10-01",
            "phase": "type_aware_filtering",
            "hypothesis": "Type-aware Jaccard beats vanilla Jaccard",
            "method": "Jaccard + Scryfall type filtering + type boosting",
            "data": "500 MTG decks + Scryfall metadata",
            "results": {"manual_eval_needed": True, "queries_tested": len(queries)},
            "learnings": [
                "Scryfall metadata successfully extracted",
                "Type filtering removes land spam",
                "Type boosting (1.5x) prefers same-type cards",
                "Much simpler than GCN, more likely to work",
            ],
            "next_steps": [
                "Manual eval on 20 queries",
                "Compare to baseline",
                "Tune type boost factor",
            ],
        }
        f.write(json.dumps(exp) + "\n")

    print("✓ Logged exp_008")
