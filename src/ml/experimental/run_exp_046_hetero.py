#!/usr/bin/env python3
"""
exp_046: Heterogeneous Graph with Deck Context (BREAKTHROUGH)

Using newly exported data with structure preserved.
Build Card-Deck-Archetype heterogeneous graph.
Expected: Beat 0.12 baseline (first improvement!)
"""

import json
from collections import defaultdict

from true_closed_loop import ClosedLoopExperiment


def heterogeneous_similarity(test_set, config):
    """Use deck context for better similarity"""

    # Load heterogeneous structure
    import pathlib

    base = pathlib.Path(__file__).resolve()
    default = base.parent.parent.parent / "src" / "backend" / "decks_hetero.jsonl"
    fixture = base.parent.parent / "tests" / "fixtures" / "decks_export_hetero_small.jsonl"
    path = default if default.exists() else fixture
    with open(path) as f:
        decks = [json.loads(line) for line in f if line.strip()]

    print(f"  Loaded {len(decks)} decks with structure")

    # Count decks with metadata
    with_archetype = sum(1 for d in decks if d.get("archetype"))
    with_format = sum(1 for d in decks if d.get("format"))
    print(f"  With archetype: {with_archetype}")
    print(f"  With format: {with_format}")

    # Build archetype-aware co-occurrence
    archetype_pairs = defaultdict(lambda: defaultdict(int))
    global_pairs = defaultdict(int)

    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    for deck in decks:
        archetype = deck.get("archetype", "Unknown")
        cards = [c["name"] for c in deck.get("cards", []) if c["name"] not in LANDS]

        # Within-deck pairs
        for i, c1 in enumerate(cards):
            for c2 in cards[i + 1 :]:
                pair = tuple(sorted([c1, c2]))
                archetype_pairs[archetype][pair] += 1
                global_pairs[pair] += 1

    print(f"  Archetypes: {len(archetype_pairs)}")
    print(f"  Global pairs: {len(global_pairs)}")

    # Evaluate: Use archetype context when available
    scores = []

    for query, labels in test_set.items():
        # Find query's archetype(s)
        query_archetypes = set()
        for deck in decks:
            if any(c["name"] == query for c in deck.get("cards", [])):
                if deck.get("archetype"):
                    query_archetypes.add(deck.get("archetype"))

        # Similarity weighted by archetype match
        card_scores = defaultdict(float)

        for archetype, pairs in archetype_pairs.items():
            arch_weight = 2.0 if archetype in query_archetypes else 1.0

            for (c1, c2), count in pairs.items():
                if c1 == query:
                    card_scores[c2] += count * arch_weight
                elif c2 == query:
                    card_scores[c1] += count * arch_weight

        if not card_scores:
            continue

        # Rank
        ranked = sorted(card_scores.items(), key=lambda x: x[1], reverse=True)

        # Score
        score = 0.0
        for card, _ in ranked[:10]:
            if card in labels.get("highly_relevant", []):
                score += 1.0
            elif card in labels.get("relevant", []):
                score += 0.75
            elif card in labels.get("somewhat_relevant", []):
                score += 0.5

        scores.append(score / 10.0)

    p10 = sum(scores) / len(scores) if scores else 0.0

    print(f"  P@10: {p10:.4f} on {len(scores)} queries")

    return {"p10": p10, "num_queries": len(scores), "archetypes_used": len(archetype_pairs)}


loop = ClosedLoopExperiment(game="magic")

results = loop.run_with_context(
    heterogeneous_similarity,
    {
        "experiment_id": "exp_046",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "heterogeneous_graph",
        "hypothesis": "Preserving deck context beats homogeneous pairs",
        "method": "Archetype-weighted similarity on heterogeneous export",
        "breakthrough": "First use of preserved structure",
    },
)

print(f"\nBREAKTHROUGH: {results['p10'] > 0.12}")
print(f"Result: P@10 = {results['p10']:.4f}")
print(f"vs Baseline: {results['p10'] - 0.12:+.4f}")
