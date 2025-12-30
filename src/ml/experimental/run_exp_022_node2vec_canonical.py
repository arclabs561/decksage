#!/usr/bin/env python3
"""
exp_022: Node2Vec on Canonical Test Set

Now that we have closed-loop + canonical test set,
re-evaluate Node2Vec honestly.
"""

from gensim.models import KeyedVectors
from true_closed_loop import ClosedLoopExperiment


def evaluate_node2vec(test_set, config):
    """Evaluate Node2Vec 39K on canonical test"""

    # Load 39K deck embeddings
    wv = KeyedVectors.load("../../data/embeddings/magic_39k_decks_pecanpy.wv")

    print(f"  Embeddings: {len(wv):,} cards")

    # Evaluate
    scores = []
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }

    for query, labels in test_set.items():
        if query not in wv:
            print(f"  Warning: {query} not in embeddings")
            continue

        # Get predictions
        preds = wv.most_similar(query, topn=10)

        # Score
        score = 0.0
        for card, _ in preds:
            for level, weight in relevance_weights.items():
                if card in labels.get(level, []):
                    score += weight
                    break

        scores.append(score / 10.0)

    avg_p10 = sum(scores) / len(scores) if scores else 0.0

    print(f"  Evaluated on {len(scores)} queries")
    print(f"  P@10: {avg_p10:.4f}")

    return {"p10": avg_p10, "num_queries_evaluated": len(scores), "method": "Node2Vec_39k_decks"}


def main():
    loop = ClosedLoopExperiment()

    exp_config = {
        "experiment_id": "exp_022",
        "date": "2025-10-01",
        "phase": "honest_reevaluation",
        "hypothesis": "Node2Vec on 39K decks with canonical test set will show true performance",
        "method": "Node2Vec (39K decks, p=1, q=1, dim=128)",
        "data": "39,384 decks",
        "key_difference": "First Node2Vec eval on canonical test set (no cherry-picking)",
    }

    results = loop.run_with_context(evaluate_node2vec, exp_config)

    print(f"\n{'=' * 60}")
    print("Honest Comparison on Same Test Set:")
    print("=" * 60)
    print("Jaccard (exp_021):  P@10 = 0.14")
    print(f"Node2Vec (exp_022): P@10 = {results['p10']:.4f}")
    print("\nBoth on same 10 queries - first fair comparison!")


if __name__ == "__main__":
    main()
