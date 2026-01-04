#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Compare hybrid embedding system vs baseline (co-occurrence only).

Shows improvement from adding instruction-tuned and GNN embeddings.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..evaluation.evaluate import compute_precision_at_k
from ..similarity.fusion import FusionWeights, WeightedLateFusion
from ..scripts.integrate_hybrid_embeddings import (
    create_fusion_with_hybrid_embeddings,
    load_hybrid_embeddings,
)
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def evaluate_baseline(
    test_set: dict,
    cooccurrence_embeddings: Any,
    adj: dict[str, set[str]],
) -> dict[str, float]:
    """Evaluate baseline (co-occurrence only)."""
    logger.info("Evaluating baseline (co-occurrence only)...")
    
    fusion = WeightedLateFusion(
        embeddings=cooccurrence_embeddings,
        adj=adj,
        weights=FusionWeights(embed=0.5, jaccard=0.5, functional=0.0),
    )
    
    scores = []
    for query, labels in test_set.items():
        try:
            results = fusion.find_similar(query, topn=10)
            candidates = [card for card, _ in results]
            p_at_10 = compute_precision_at_k(candidates, labels, k=10)
            scores.append(p_at_10)
        except Exception:
            continue
    
    avg_p_at_10 = sum(scores) / len(scores) if scores else 0.0
    return {
        "avg_p_at_10": avg_p_at_10,
        "evaluated": len(scores),
    }


def evaluate_hybrid(
    test_set: dict,
    embeddings_data: dict[str, Any],
    adj: dict[str, set[str]],
) -> dict[str, float]:
    """Evaluate hybrid system."""
    logger.info("Evaluating hybrid system...")
    
    fusion = create_fusion_with_hybrid_embeddings(
        embeddings_data,
        adj=adj,
    )
    
    scores = []
    for query, labels in test_set.items():
        try:
            results = fusion.find_similar(query, topn=10)
            candidates = [card for card, _ in results]
            p_at_10 = compute_precision_at_k(candidates, labels, k=10)
            scores.append(p_at_10)
        except Exception:
            continue
    
    avg_p_at_10 = sum(scores) / len(scores) if scores else 0.0
    return {
        "avg_p_at_10": avg_p_at_10,
        "evaluated": len(scores),
    }


def main() -> int:
    """Compare baseline vs hybrid."""
    parser = argparse.ArgumentParser(description="Compare hybrid vs baseline")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=PATHS.experiments / "test_set_canonical_magic.json",
        help="Test set path",
    )
    parser.add_argument(
        "--cooccurrence-embeddings",
        type=Path,
        help="Co-occurrence embeddings path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "hybrid_vs_baseline_comparison.json",
        help="Output path",
    )
    
    args = parser.parse_args()
    
    # Load test set
    if not args.test_set.exists():
        logger.error(f"Test set not found: {args.test_set}")
        return 1
    
    with open(args.test_set) as f:
        test_data = json.load(f)
    test_set = test_data.get("queries", test_data)
    
    logger.info(f"Loaded {len(test_set)} test queries")
    
    # Load baseline embeddings
    baseline_embeddings = None
    adj = {}
    if args.cooccurrence_embeddings and args.cooccurrence_embeddings.exists():
        try:
            from gensim.models import KeyedVectors
            baseline_embeddings = KeyedVectors.load(str(args.cooccurrence_embeddings))
            logger.info(f"Loaded baseline embeddings: {len(baseline_embeddings)} cards")
        except Exception as e:
            logger.warning(f"Failed to load baseline: {e}")
    
    # Evaluate baseline
    baseline_results = {}
    if baseline_embeddings:
        baseline_results = evaluate_baseline(test_set, baseline_embeddings, adj)
        logger.info(f"Baseline P@10: {baseline_results['avg_p_at_10']:.4f}")
    
    # Evaluate hybrid
    embeddings_data = load_hybrid_embeddings(
        cooccurrence_embeddings_path=args.cooccurrence_embeddings,
    )
    hybrid_results = evaluate_hybrid(test_set, embeddings_data, adj)
    logger.info(f"Hybrid P@10: {hybrid_results['avg_p_at_10']:.4f}")
    
    # Comparison
    print()
    print("="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    if baseline_results:
        improvement = (
            (hybrid_results["avg_p_at_10"] - baseline_results["avg_p_at_10"])
            / baseline_results["avg_p_at_10"]
            * 100
        )
        print(f"Baseline (co-occurrence only):  P@10 = {baseline_results['avg_p_at_10']:.4f}")
        print(f"Hybrid (all three signals):     P@10 = {hybrid_results['avg_p_at_10']:.4f}")
        print(f"Improvement:                     {improvement:+.1f}%")
    else:
        print(f"Hybrid system:                   P@10 = {hybrid_results['avg_p_at_10']:.4f}")
    print("="*70)
    
    # Save results
    results = {
        "baseline": baseline_results,
        "hybrid": hybrid_results,
        "improvement_percent": (
            (hybrid_results["avg_p_at_10"] - baseline_results["avg_p_at_10"])
            / baseline_results["avg_p_at_10"]
            * 100
            if baseline_results and baseline_results["avg_p_at_10"] > 0
            else None
        ),
    }
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

