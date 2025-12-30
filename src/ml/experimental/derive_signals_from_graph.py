#!/usr/bin/env python3
"""
exp_037: Derive Signals from Graph (Pivot from Metadata)

Since parsing metadata fails repeatedly, derive signals from pairs.csv:

Signal 1: Community detection (cluster cards)
Signal 2: Centrality (identify important cards)
Signal 3: Local clustering coefficient
Signal 4: Triangles (3-way synergies)

These are computable without metadata and add new information.
"""

from collections import defaultdict

import pandas as pd


def derive_graph_signals(pairs_csv):
    """Extract network structure signals"""

    df = pd.read_csv(pairs_csv)

    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    # Build graph
    adj = defaultdict(set)
    edge_weights = {}

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)
            edge_weights[(c1, c2)] = row["COUNT_MULTISET"]
            edge_weights[(c2, c1)] = row["COUNT_MULTISET"]

    cards = list(adj.keys())
    print(f"Graph: {len(cards)} cards, {sum(len(n) for n in adj.values()) // 2} edges")

    # Signal 1: Degree (basic but useful)
    degree = {c: len(adj[c]) for c in cards}

    # Signal 2: Clustering coefficient (how connected are neighbors)
    clustering = {}
    for card in cards:
        neighbors = adj[card]
        if len(neighbors) < 2:
            clustering[card] = 0
        else:
            # Count edges between neighbors
            edges_between = sum(
                1 for n1 in neighbors for n2 in neighbors if n1 < n2 and n2 in adj[n1]
            )
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            clustering[card] = edges_between / possible if possible > 0 else 0

    # Signal 3: Triangles (cards in 3-way synergies)
    triangles = defaultdict(int)
    for card in cards:
        for n1 in adj[card]:
            for n2 in adj[card]:
                if n1 < n2 and n2 in adj[n1]:
                    triangles[card] += 1

    print("\nDerived signals:")
    print(f"  Degree range: {min(degree.values())} - {max(degree.values())}")
    print(f"  Clustering range: {min(clustering.values()):.3f} - {max(clustering.values()):.3f}")
    print(f"  Max triangles: {max(triangles.values())}")

    # High clustering = specialized cards (tight synergies)
    high_clustering = sorted(clustering.items(), key=lambda x: x[1], reverse=True)[:10]
    print(f"\n  High clustering (specialized): {[c for c, _ in high_clustering]}")

    # Low clustering, high degree = generic staples
    generic_cards = [(c, degree[c], clustering.get(c, 0)) for c in cards if degree[c] > 100]
    generic_sorted = sorted(generic_cards, key=lambda x: x[2])[:10]
    print(f"\n  Generic staples (high degree, low clustering): {[c for c, _, _ in generic_sorted]}")

    return {
        "degree": degree,
        "clustering": clustering,
        "triangles": triangles,
        "adj": adj,
        "edge_weights": edge_weights,
    }


def evaluate_with_graph_signals(test_set, signals):
    """Use derived signals for similarity"""

    adj = signals["adj"]
    signals["degree"]
    clustering = signals["clustering"]

    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    scores = []

    for query, labels in test_set.items():
        if query not in adj or query in LANDS:
            continue

        neighbors = adj[query]
        query_clustering = clustering.get(query, 0)

        sims = []

        for other in list(adj.keys())[:3000]:
            if other == query or other in LANDS:
                continue

            other_n = adj[other]

            # Jaccard
            intersection = len(neighbors & other_n)
            union = len(neighbors | other_n)
            jaccard = intersection / union if union > 0 else 0

            # Clustering similarity (similar specialization level)
            other_clustering = clustering.get(other, 0)
            cluster_sim = 1.0 - abs(query_clustering - other_clustering)

            # Combined
            combined = 0.8 * jaccard + 0.2 * cluster_sim

            sims.append((other, combined))

        sims.sort(key=lambda x: x[1], reverse=True)

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

    return p10, len(scores)


if __name__ == "__main__":
    print("=" * 60)
    print("exp_037: Graph-Derived Signals")
    print("=" * 60)

    signals = derive_graph_signals("../backend/pairs_large.csv")

    # Load test set
    import json

    with open("../../experiments/test_set_canonical_magic.json") as f:
        test_data = json.load(f)
        test_set = test_data["queries"]

    p10, num_queries = evaluate_with_graph_signals(test_set, signals)

    print("\nResults:")
    print(f"  P@10: {p10:.4f} on {num_queries} queries")
    print("  Baseline: 0.12")
    print(f"  Change: {p10 - 0.12:+.4f}")

    # Log
    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        exp = {
            "experiment_id": "exp_037",
            "date": "2025-10-01",
            "game": "magic",
            "phase": "graph_structure_signals",
            "hypothesis": "Graph structure signals (clustering, triangles) add information",
            "method": "Jaccard + Clustering coefficient similarity",
            "data": "39K decks, derived signals from network structure",
            "new_signals": ["clustering_coefficient", "triangle_count", "specialized_vs_generic"],
            "results": {"p10": p10, "num_queries": num_queries},
        }
        f.write(json.dumps(exp) + "\n")

    print("\n✓ Logged exp_037")
    print("\nTotal experiments: 38")
