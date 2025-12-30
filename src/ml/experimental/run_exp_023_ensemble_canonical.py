#!/usr/bin/env python3
"""
exp_023: Ensemble on Canonical Test Set

Hypothesis: Ensemble voting (from exp_015) will beat single methods on canonical test.
Uses: DeepWalk, Node2Vec (4 variants), Jaccard = 5 methods
"""

from collections import defaultdict

import pandas as pd
from gensim.models import KeyedVectors
from true_closed_loop import ClosedLoopExperiment


def evaluate_ensemble(test_set, config):
    """Ensemble of all methods"""

    # Load all methods
    methods = {}

    for name in ["deepwalk", "node2vec_default", "node2vec_bfs", "node2vec_dfs"]:
        try:
            methods[name] = KeyedVectors.load(f"../../data/embeddings/{name}.wv")
            print(f"  Loaded {name}")
        except:
            print(f"  Missing {name}")

    # Jaccard
    df = pd.read_csv("../backend/pairs_large.csv")
    adj = defaultdict(set)
    LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        if c1 not in LANDS and c2 not in LANDS:
            adj[c1].add(c2)
            adj[c2].add(c1)

    print("  Built Jaccard graph")

    # Evaluate ensemble
    scores = []
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }

    for query, labels in test_set.items():
        # Collect votes from all methods
        votes = defaultdict(float)

        # Embedding methods
        for wv in methods.values():
            if query in wv:
                preds = wv.most_similar(query, topn=10)
                for rank, (card, score) in enumerate(preds, 1):
                    votes[card] += 1.0 / rank

        # Jaccard
        if query in adj:
            neighbors = adj[query]
            jac_sims = []
            for other in list(adj.keys())[:2000]:
                if other != query:
                    other_n = adj[other]
                    i = len(neighbors & other_n)
                    u = len(neighbors | other_n)
                    if u > 0:
                        jac_sims.append((other, i / u))
            jac_sims.sort(key=lambda x: x[1], reverse=True)
            for rank, (card, score) in enumerate(jac_sims[:10], 1):
                votes[card] += 1.0 / rank

        # Get top-10 by votes
        top10 = sorted(votes.items(), key=lambda x: x[1], reverse=True)[:10]

        # Score
        score = 0.0
        for card, _ in top10:
            for level, weight in relevance_weights.items():
                if card in labels.get(level, []):
                    score += weight
                    break

        scores.append(score / 10.0)

    avg_p10 = sum(scores) / len(scores) if scores else 0.0

    print(f"  Evaluated on {len(scores)} queries")
    print(f"  P@10: {avg_p10:.4f}")

    return {
        "p10": avg_p10,
        "num_queries_evaluated": len(scores),
        "num_methods_ensembled": len(methods) + 1,
        "method": "Ensemble_5_methods",
    }


def main():
    loop = ClosedLoopExperiment(game="magic")

    exp_config = {
        "experiment_id": "exp_023",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "ensemble_on_canonical",
        "hypothesis": "Ensemble voting beats single methods",
        "method": "Ensemble (DeepWalk + Node2Vec x4 + Jaccard)",
        "data": "39,384 MTG decks",
        "test_set": "canonical_magic (10 queries)",
        "learnings_applied": ["Ensemble from exp_015", "Canonical test set", "Land filtering"],
    }

    results = loop.run_with_context(evaluate_ensemble, exp_config)

    print(f"\n{'=' * 60}")
    print("Fair Comparison (Same Test Set):")
    print("=" * 60)
    print("Jaccard alone:  P@10 = 0.14")
    print("Node2Vec alone: P@10 = 0.06")
    print(f"Ensemble:       P@10 = {results['p10']:.4f}")


if __name__ == "__main__":
    main()
