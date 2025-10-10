#!/usr/bin/env python3
"""Run tests without pytest - simple assertions."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.constants import GAME_FILTERS, RELEVANCE_WEIGHTS, get_filter_set
from utils.evaluation import compute_precision_at_k, evaluate_similarity, jaccard_similarity

passed = 0
failed = 0


def test(name, condition, error_msg=""):
    global passed, failed
    if condition:
        print(f"✓ {name}")
        passed += 1
    else:
        print(f"✗ {name}: {error_msg}")
        failed += 1


print("Testing constants...")

# Game filters exist
test("Game filters exist", all(g in GAME_FILTERS for g in ["magic", "yugioh", "pokemon"]))

# Magic filters
basic = get_filter_set("magic", "basic")
test("Magic basic lands", "Plains" in basic and len(basic) == 5)

common = get_filter_set("magic", "common")
test("Magic common lands", "Snow-Covered Plains" in common and len(common) > len(basic))

all_filters = get_filter_set("magic", "all")
test("Magic all filters", "Command Tower" in all_filters and len(all_filters) > len(common))

# Pokemon filters
energy = get_filter_set("pokemon", "basic")
test("Pokemon energy", "Fire Energy" in energy and len(energy) == 9)

# YGO filters
ygo = get_filter_set("yugioh", "basic")
test("YuGiOh filters", isinstance(ygo, set))

# Relevance weights
test(
    "Relevance weights ordered",
    RELEVANCE_WEIGHTS["highly_relevant"] == 1.0 and RELEVANCE_WEIGHTS["irrelevant"] == 0.0,
)

# Case insensitive
test("Case insensitive", get_filter_set("MAGIC", "basic") == get_filter_set("magic", "basic"))

# Unknown game/level
test("Unknown game", get_filter_set("unknown", "basic") == set())

test("Unknown level", get_filter_set("magic", "nonexistent") == set())

print("\nTesting evaluation...")

# Precision@K perfect
predictions = ["card1", "card2", "card3"]
labels = {"highly_relevant": ["card1", "card2", "card3"]}
score = compute_precision_at_k(predictions, labels, k=3)
test("Perfect P@K", abs(score - 1.0) < 0.001)

# Precision@K none
predictions = ["card1", "card2", "card3"]
labels = {"highly_relevant": ["other1"], "irrelevant": ["card1", "card2", "card3"]}
score = compute_precision_at_k(predictions, labels, k=3)
test("Zero P@K", abs(score - 0.0) < 0.001)

# Weighted
predictions = ["card1", "card2", "card3"]
labels = {
    "highly_relevant": ["card1"],  # 1.0
    "relevant": ["card2"],  # 0.75
    "somewhat_relevant": ["card3"],  # 0.5
}
score = compute_precision_at_k(predictions, labels, k=3)
expected = (1.0 + 0.75 + 0.5) / 3
test("Weighted P@K", abs(score - expected) < 0.001, f"got {score}, expected {expected}")

# Jaccard identical
set1 = {"a", "b", "c"}
set2 = {"a", "b", "c"}
test("Jaccard identical", jaccard_similarity(set1, set2) == 1.0)

# Jaccard disjoint
set1 = {"a", "b", "c"}
set2 = {"d", "e", "f"}
test("Jaccard disjoint", jaccard_similarity(set1, set2) == 0.0)

# Jaccard partial
set1 = {"a", "b", "c"}
set2 = {"b", "c", "d"}
test("Jaccard partial", jaccard_similarity(set1, set2) == 0.5)

# Jaccard empty
test("Jaccard empty", jaccard_similarity(set(), set()) == 0.0)

# Evaluate similarity
test_set = {"query1": {"highly_relevant": ["result1", "result2"]}}


def dummy_sim(query, k):
    return [("result1", 0.9), ("result2", 0.8), ("wrong", 0.7)]


results = evaluate_similarity(test_set, dummy_sim, top_k=3)
test(
    "Evaluate similarity",
    "p@3" in results and results["num_queries"] == 1 and results["num_evaluated"] == 1,
)

print(f"\n{'=' * 50}")
print(f"Results: {passed} passed, {failed} failed")
print("=" * 50)

sys.exit(0 if failed == 0 else 1)
