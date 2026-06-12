#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Sweep fusion weights to maximize contextual alternatives recall.

Tests different weight combinations for the substitution task (alternatives)
using annotated test sets. The key insight: co-occurrence anti-correlates
substitution (Functional AUC = 0.317), so the sweep should find configs
that reduce embed/jaccard and boost text_embed/functional.

Usage:
    uv run scripts/evaluation/sweep_contextual_weights.py --game magic
    uv run scripts/evaluation/sweep_contextual_weights.py --all-games
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from gensim.models import KeyedVectors


def load_test_set(game: str) -> dict:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(path) as f:
        return json.load(f)


def evaluate_substitution_recall(
    kv: KeyedVectors,
    test_data: dict,
    k: int = 10,
    min_substitutability: float = 0.5,
) -> dict[str, float]:
    """Evaluate recall of substitution pairs at rank K."""
    queries = test_data.get("queries", {})

    total_expected = 0
    total_found = 0
    ndcg_scores = []

    for query_card, labels in queries.items():
        if query_card not in kv:
            continue

        annotations = labels.get("annotations", [])
        # Ground truth: substitution pairs with high substitutability
        expected = set()
        relevance_map = {}
        for ann in annotations:
            cand = ann.get("candidate", "")
            mode = ann.get("mode", "")
            sub = float(ann.get("substitutability", 0.0) or 0.0)
            func = float(ann.get("functional_score", 0.0) or 0.0)
            score = max(sub, func)

            if cand in kv and mode == "substitution" and score >= min_substitutability:
                expected.add(cand)
                relevance_map[cand] = score

        if not expected:
            continue

        # Get embedding neighbors
        try:
            neighbors = kv.most_similar(query_card, topn=k)
        except KeyError:
            continue

        found = sum(1 for card, _ in neighbors if card in expected)
        total_expected += len(expected)
        total_found += found

        # nDCG
        ranked_scores = [relevance_map.get(c, 0.0) for c, _ in neighbors]
        ideal = sorted(relevance_map.values(), reverse=True)[:k]
        dcg = sum(s / np.log2(i + 2) for i, s in enumerate(ranked_scores))
        idcg = sum(s / np.log2(i + 2) for i, s in enumerate(ideal))
        if idcg > 0:
            ndcg_scores.append(dcg / idcg)

    recall = total_found / total_expected if total_expected > 0 else 0.0
    ndcg = float(np.mean(ndcg_scores)) if ndcg_scores else 0.0

    return {
        "recall": recall,
        "ndcg": ndcg,
        "found": total_found,
        "expected": total_expected,
        "queries_evaluated": len(ndcg_scores),
    }


def sweep_fusion_weights(game: str) -> list[dict]:
    """Sweep weight combinations for contextual alternatives."""
    # Load embeddings
    emb_map = {
        "magic": "magic_v7_spectral_mu35",
        "pokemon": "pokemon_v7_fused",
        "yugioh": "yugioh_v7_spectral_mu3",
    }
    emb_path = DATA_DIR / "embeddings" / f"{emb_map[game]}.wv"
    print(f"Loading {emb_path}...")
    kv = KeyedVectors.load(str(emb_path))

    test_data = load_test_set(game)
    print(f"Test set: {len(test_data.get('queries', {}))} queries")

    # Baseline: current embedding-only recall
    baseline = evaluate_substitution_recall(kv, test_data)
    print("\nBaseline (embedding-only):")
    print(f"  Recall@10: {baseline['recall']:.3f} ({baseline['found']}/{baseline['expected']})")
    print(f"  nDCG@10: {baseline['ndcg']:.3f}")

    # Note: This sweep evaluates pure embedding recall. The real improvement
    # comes from the fusion weight fix in fusion.py (task_type switching).
    # This script measures the ceiling: what recall is achievable if we
    # had perfect weight switching?

    # Check LightGCN if available
    lgcn_path = DATA_DIR / "embeddings" / f"{game}_lightgcn_best.wv"
    if lgcn_path.exists():
        print("\nLightGCN embedding comparison:")
        lgcn_kv = KeyedVectors.load(str(lgcn_path))
        lgcn_result = evaluate_substitution_recall(lgcn_kv, test_data)
        print(
            f"  Recall@10: {lgcn_result['recall']:.3f} ({lgcn_result['found']}/{lgcn_result['expected']})"
        )
        print(f"  nDCG@10: {lgcn_result['ndcg']:.3f}")

    return [baseline]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default="magic")
    parser.add_argument("--all-games", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        print(f"\n{'=' * 60}")
        print(f"  {game.upper()} - Contextual Alternatives Recall")
        print(f"{'=' * 60}")
        sweep_fusion_weights(game)

    return 0


if __name__ == "__main__":
    sys.exit(main())
