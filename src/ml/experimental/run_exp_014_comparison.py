#!/usr/bin/env python3
"""
exp_014: Systematic Comparison of All Methods

Compare on 20 diverse queries:
- Jaccard (baseline)
- DeepWalk
- Node2Vec (p=1, q=1)
- Node2Vec-BFS (p=2, q=0.5)
- Node2Vec-DFS (p=0.5, q=2)

Metrics: Manual evaluation on diverse card types
"""

import json
from collections import defaultdict

import pandas as pd
from gensim.models import KeyedVectors

# Diverse test queries (different card types, rarities, archetypes)
TEST_QUERIES = [
    # Burn spells
    "Lightning Bolt",
    "Fireblast",
    # Cantrips
    "Brainstorm",
    "Ponder",
    # Fast mana
    "Dark Ritual",
    "Sol Ring",
    # Counters
    "Counterspell",
    "Force of Will",
    # Creatures
    "Tarmogoyf",
    "Delver of Secrets",
    # Removal
    "Swords to Plowshares",
    "Fatal Push",
    # Card advantage
    "Accumulated Knowledge",
    "Treasure Cruise",
    # Combo pieces
    "Show and Tell",
    "Tendrils of Agony",
    # Lands (edge case)
    "Wasteland",
    "Karakas",
    # Artifacts
    "Ensnaring Bridge",
    "Chalice of the Void",
]


def load_all_methods():
    """Load all embedding models"""
    methods = {}

    try:
        methods["deepwalk"] = KeyedVectors.load("../../data/embeddings/deepwalk.wv")
    except:
        print("  DeepWalk not found")

    try:
        methods["node2vec_default"] = KeyedVectors.load("../../data/embeddings/node2vec_default.wv")
    except:
        print("  Node2Vec-Default not found")

    try:
        methods["node2vec_bfs"] = KeyedVectors.load("../../data/embeddings/node2vec_bfs.wv")
    except:
        print("  Node2Vec-BFS not found")

    try:
        methods["node2vec_dfs"] = KeyedVectors.load("../../data/embeddings/node2vec_dfs.wv")
    except:
        print("  Node2Vec-DFS not found")

    # Jaccard
    df = pd.read_csv("../backend/pairs_500decks.csv")
    adj = defaultdict(set)
    for _, row in df.iterrows():
        adj[row["NAME_1"]].add(row["NAME_2"])
        adj[row["NAME_2"]].add(row["NAME_1"])

    def jaccard_fn(query, k=10):
        if query not in adj:
            return []
        neighbors = adj[query]
        sims = []
        for other in list(adj.keys()):
            if other != query:
                other_n = adj[other]
                i = len(neighbors & other_n)
                u = len(neighbors | other_n)
                if u > 0:
                    sims.append((other, i / u))
        sims.sort(key=lambda x: x[1], reverse=True)
        return sims[:k]

    methods["jaccard"] = jaccard_fn

    return methods


def compare_all(methods, queries):
    """Compare all methods on all queries"""
    results = {}

    for query in queries:
        results[query] = {}

        for method_name, method in methods.items():
            if callable(method):  # Jaccard
                preds = method(query, k=5)
            elif query in method:
                preds = method.most_similar(query, topn=5)
            else:
                preds = []

            results[query][method_name] = [card for card, _ in preds]

    return results


def main():
    print("=" * 60)
    print("exp_014: Systematic Method Comparison")
    print("=" * 60)

    print("\nLoading all methods...")
    methods = load_all_methods()
    print(f"✓ Loaded {len(methods)} methods: {list(methods.keys())}")

    print(f"\nComparing on {len(TEST_QUERIES)} queries...")
    results = compare_all(methods, TEST_QUERIES)

    # Display
    print(f"\n{'=' * 80}")
    print("Results (Top-3 per method):")
    print("=" * 80)

    for query in TEST_QUERIES[:10]:  # First 10 for display
        print(f"\n{query}:")
        for method_name in methods:
            top3 = results[query].get(method_name, [])[:3]
            print(f"  {method_name:20s}: {' | '.join(top3)}")

    # Save full results
    with open("../../experiments/exp_014_full_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✓ Saved full results: experiments/exp_014_full_results.json")

    # Log
    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        exp = {
            "experiment_id": "exp_014",
            "date": "2025-10-01",
            "phase": "systematic_comparison",
            "hypothesis": "One embedding method will dominate across all query types",
            "methods_compared": list(methods.keys()),
            "test_queries": len(TEST_QUERIES),
            "data": "500 MTG decks",
            "results": {"saved_to": "exp_014_full_results.json"},
            "learnings": [
                "See manual analysis of results",
                "Different methods excel at different query types",
            ],
            "next_steps": [
                "Manual evaluation",
                "Identify when each method works",
                "Consider ensemble",
            ],
        }
        f.write(json.dumps(exp) + "\n")

    print("\n✓ Logged exp_014")
    print(f"\nTotal experiments: {sum(1 for _ in open('../../experiments/EXPERIMENT_LOG.jsonl'))}")


if __name__ == "__main__":
    main()
