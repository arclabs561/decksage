#!/usr/bin/env python3
"""
Experiment: Format-Specific Card Similarity

Hypothesis: Filtering to specific format (Modern, Legacy, etc) will improve
P@10 over generic co-occurrence because it removes cross-format contamination.

Test: Build separate graphs for Modern, Legacy, Pauper and evaluate on
test set queries relevant to each format.
"""

import json
from collections import defaultdict
from pathlib import Path

from utils.evaluation import compute_precision_at_k, jaccard_similarity

from ml.utils.shared_operations import jaccard_similarity


def load_decks_by_format(jsonl_path):
    """Load decks grouped by format"""
    decks_by_format = defaultdict(list)

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)
            fmt = deck.get("format", "unknown")
            cards = [c["name"] for c in deck.get("cards", [])]
            decks_by_format[fmt].append(cards)

    return decks_by_format


def build_cooccurrence_graph(decks):
    """Build card co-occurrence graph from decks"""
    graph = defaultdict(set)

    for deck in decks:
        unique_cards = set(deck)
        for card in unique_cards:
            graph[card].update(unique_cards - {card})

    return graph


def find_similar_cards(card, graph, top_k=10):
    """Find similar cards using Jaccard similarity on co-occurrence"""
    if card not in graph:
        return []

    neighbors = graph[card]
    similarities = []

    for other_card in graph:
        if other_card == card:
            continue

        sim = jaccard_similarity(neighbors, graph[other_card])
        if sim > 0:
            similarities.append((other_card, sim))

    similarities.sort(key=lambda x: -x[1])
    return [c for c, _ in similarities[:top_k]]


def evaluate_on_test_set(graph, test_set_path):
    """Evaluate P@K on test set"""
    with open(test_set_path) as f:
        test_data = json.load(f)

    queries = test_data.get("queries", {})
    results = {}

    for query_card, ground_truth in queries.items():
        predictions = find_similar_cards(query_card, graph, top_k=10)

        # compute_precision_at_k expects labels dict
        labels = {
            "highly_relevant": ground_truth.get("highly_relevant", []),
            "relevant": ground_truth.get("relevant", []),
            "somewhat_relevant": ground_truth.get("somewhat_relevant", []),
        }

        # Weights for each relevance level
        weights = {"highly_relevant": 1.0, "relevant": 0.7, "somewhat_relevant": 0.4}

        p10 = compute_precision_at_k(predictions, labels, k=10, weights=weights)
        results[query_card] = p10

    avg_p10 = sum(results.values()) / len(results) if results else 0
    return avg_p10, results


def main():
    # Paths
    data_path = Path("../../data/processed/decks_with_metadata.jsonl")
    test_set_path = Path("../../experiments/test_set_unified_magic.json")

    print("Loading decks by format...")
    decks_by_format = load_decks_by_format(data_path)

    print("\nFormats found:")
    for fmt, decks in sorted(decks_by_format.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {fmt}: {len(decks)} decks")

    # Experiment 1: All decks (baseline)
    print("\n" + "=" * 60)
    print("Baseline: All decks combined")
    print("=" * 60)
    all_decks = []
    for decks in decks_by_format.values():
        all_decks.extend(decks)

    print(f"Building graph from {len(all_decks)} decks...")
    all_graph = build_cooccurrence_graph(all_decks)
    print(f"Graph: {len(all_graph)} cards")

    p10_all, _ = evaluate_on_test_set(all_graph, test_set_path)
    print(f"P@10: {p10_all:.4f}")

    # Experiment 2: Modern only
    if "Modern" in decks_by_format:
        print("\n" + "=" * 60)
        print("Format-Specific: Modern only")
        print("=" * 60)
        modern_decks = decks_by_format["Modern"]
        print(f"Building graph from {len(modern_decks)} Modern decks...")
        modern_graph = build_cooccurrence_graph(modern_decks)
        print(f"Graph: {len(modern_graph)} cards")

        p10_modern, _ = evaluate_on_test_set(modern_graph, test_set_path)
        print(f"P@10: {p10_modern:.4f}")

        if p10_modern > p10_all:
            improvement = (p10_modern / p10_all - 1) * 100
            print(f"✓ Improvement: +{improvement:.1f}%")
        else:
            decline = (1 - p10_modern / p10_all) * 100
            print(f"✗ Decline: -{decline:.1f}%")

    # Experiment 3: Legacy only
    if "Legacy" in decks_by_format:
        print("\n" + "=" * 60)
        print("Format-Specific: Legacy only")
        print("=" * 60)
        legacy_decks = decks_by_format["Legacy"]
        print(f"Building graph from {len(legacy_decks)} Legacy decks...")
        legacy_graph = build_cooccurrence_graph(legacy_decks)
        print(f"Graph: {len(legacy_graph)} cards")

        p10_legacy, _ = evaluate_on_test_set(legacy_graph, test_set_path)
        print(f"P@10: {p10_legacy:.4f}")

        if p10_legacy > p10_all:
            improvement = (p10_legacy / p10_all - 1) * 100
            print(f"✓ Improvement: +{improvement:.1f}%")
        else:
            decline = (1 - p10_legacy / p10_all) * 100
            print(f"✗ Decline: -{decline:.1f}%")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Baseline (all formats): P@10 = {p10_all:.4f}")
    if "Modern" in decks_by_format:
        print(f"Modern only: P@10 = {p10_modern:.4f}")
    if "Legacy" in decks_by_format:
        print(f"Legacy only: P@10 = {p10_legacy:.4f}")


if __name__ == "__main__":
    main()
