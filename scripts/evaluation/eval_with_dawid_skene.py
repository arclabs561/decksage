#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Compare nDCG using raw scores vs Dawid-Skene consensus-weighted scores.

Tests whether probabilistic aggregation of multi-judge annotations
produces better ground truth than naive averaging.

Uses per-model reliability from Dawid-Skene (experiment 0027):
- claude_sonnet_4_6: 0.831 (most reliable)
- gpt_5_2: 0.636
- gemini_3_1_pro: 0.536
- deepseek_v3_2: 0.495

Usage:
    uv run scripts/evaluation/eval_with_dawid_skene.py --game magic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Per-model reliability weights from Dawid-Skene analysis
MODEL_RELIABILITY = {
    "claude_sonnet_4_6": 0.831,
    "anthropic/claude-sonnet-4.5": 0.831,
    "anthropic/claude-haiku-4.5": 0.75,  # estimated (close to sonnet)
    "gpt_5_2": 0.636,
    "openai/gpt-4o-mini": 0.636,
    "openai/gpt-4.1-nano": 0.636,
    "gemini_3_1_pro": 0.536,
    "google/gemini-2.0-flash-lite": 0.536,
    "deepseek_v3_2": 0.495,
    "deepseek/deepseek-chat-v3": 0.495,
}


def dcg(scores: list[float], k: int = 10) -> float:
    return sum(s / np.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg(relevances: list[float], ideal: list[float], k: int = 10) -> float:
    idcg = dcg(sorted(ideal, reverse=True), k)
    return dcg(relevances, k) / idcg if idcg > 0 else 0.0


def get_reliability_weight(model_name: str) -> float:
    """Get reliability weight for an LLM model."""
    for key, weight in MODEL_RELIABILITY.items():
        if key in (model_name or "").lower() or (model_name or "") == key:
            return weight
    return 0.5  # default for unknown models


def eval_game(game: str, embedding_name: str, k: int = 10) -> dict:
    """Run nDCG comparison: raw scores vs reliability-weighted."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        test_data = json.load(f)

    emb_path = DATA_DIR / "embeddings" / f"{embedding_name}.wv"
    kv = KeyedVectors.load(str(emb_path))

    queries = test_data.get("queries", {})

    raw_ndcg_scores = []
    weighted_ndcg_scores = []

    for qname, qdata in queries.items():
        if qname not in kv:
            continue
        annotations = qdata.get("annotations", [])
        if not annotations:
            continue

        # Build ground truth: raw (naive mean) vs weighted (reliability-adjusted)
        raw_gt = {}
        weighted_gt = {}
        for ann in annotations:
            c = ann.get("candidate", "")
            s = ann.get("similarity_score")
            model = ann.get("llm_model", "")
            if s is None or not c:
                continue
            score = float(s)
            weight = get_reliability_weight(model)

            # Raw: use score as-is
            if c not in raw_gt:
                raw_gt[c] = []
            raw_gt[c].append(score)

            # Weighted: scale by reliability
            if c not in weighted_gt:
                weighted_gt[c] = {"total": 0.0, "weight": 0.0}
            weighted_gt[c]["total"] += score * weight
            weighted_gt[c]["weight"] += weight

        raw_gt_final = {c: np.mean(scores) for c, scores in raw_gt.items()}
        weighted_gt_final = {
            c: v["total"] / v["weight"] if v["weight"] > 0 else 0.0 for c, v in weighted_gt.items()
        }

        # Get embedding ranking
        try:
            neighbors = kv.most_similar(qname, topn=k)
        except KeyError:
            continue

        # nDCG with raw scores
        raw_rel = [raw_gt_final.get(c, 0.0) for c, _ in neighbors]
        raw_ideal = sorted(raw_gt_final.values(), reverse=True)
        if max(raw_ideal[:k]) > 0:
            raw_ndcg_scores.append(ndcg(raw_rel, raw_ideal, k))

        # nDCG with weighted scores
        w_rel = [weighted_gt_final.get(c, 0.0) for c, _ in neighbors]
        w_ideal = sorted(weighted_gt_final.values(), reverse=True)
        if max(w_ideal[:k]) > 0:
            weighted_ndcg_scores.append(ndcg(w_rel, w_ideal, k))

    return {
        "raw_ndcg": float(np.mean(raw_ndcg_scores)) if raw_ndcg_scores else 0.0,
        "raw_n": len(raw_ndcg_scores),
        "weighted_ndcg": float(np.mean(weighted_ndcg_scores)) if weighted_ndcg_scores else 0.0,
        "weighted_n": len(weighted_ndcg_scores),
        "delta": (float(np.mean(weighted_ndcg_scores)) - float(np.mean(raw_ndcg_scores)))
        if raw_ndcg_scores and weighted_ndcg_scores
        else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default="magic")
    parser.add_argument("--embedding", default="magic_v5_fused")
    args = parser.parse_args()

    print("Comparing raw vs reliability-weighted nDCG")
    print(f"Game: {args.game}, Embedding: {args.embedding}")
    print()

    result = eval_game(args.game, args.embedding)

    print(f"Raw nDCG@10:      {result['raw_ndcg']:.4f} (n={result['raw_n']})")
    print(f"Weighted nDCG@10: {result['weighted_ndcg']:.4f} (n={result['weighted_n']})")
    print(f"Delta:            {result['delta']:+.4f}")
    print()

    if abs(result["delta"]) < 0.005:
        print("Conclusion: negligible difference -- single-model annotations dominate")
    elif result["delta"] > 0:
        print("Conclusion: reliability weighting IMPROVES nDCG")
    else:
        print("Conclusion: reliability weighting HURTS nDCG (check weights)")

    # Also test with MetaPath2Vec
    mp_emb = f"{args.game}_metapath2vec"
    mp_path = DATA_DIR / "embeddings" / f"{mp_emb}.wv"
    if mp_path.exists():
        print("\n--- MetaPath2Vec comparison ---")
        mp_result = eval_game(args.game, mp_emb)
        print(f"Raw nDCG@10:      {mp_result['raw_ndcg']:.4f}")
        print(f"Weighted nDCG@10: {mp_result['weighted_ndcg']:.4f}")
        print(f"Delta:            {mp_result['delta']:+.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
