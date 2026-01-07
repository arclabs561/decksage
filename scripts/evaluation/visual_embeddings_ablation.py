#!/usr/bin/env python3
"""
Ablation study for visual embeddings.

Measures contribution of visual embeddings at different weight levels.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths
    setup_project_paths()
except ImportError:
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

import argparse
import json
import logging
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def evaluate_with_visual_weight(
    test_set_path: Path,
    embeddings_path: Path,
    pairs_path: Path,
    visual_weight: float,
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate fusion with specific visual embedding weight."""
    logger.info(f"Evaluating with visual_weight={visual_weight:.2f}...")
    
    try:
        from ml.evaluation.similarity_helper import create_similarity_function
        from ml.utils.evaluation import evaluate_similarity
        from ml.similarity.fusion import FusionWeights
        
        # Load test set
        with open(test_set_path) as f:
            test_set = json.load(f)
        
        # Create weights with specified visual weight
        weights = FusionWeights(
            embed=0.20,
            jaccard=0.15,
            functional=0.10,
            text_embed=0.25,
            visual_embed=visual_weight,
            gnn=0.30,
        ).normalized()
        
        # Create similarity function
        similarity_fn = create_similarity_function(
            embeddings_path=embeddings_path,
            pairs_path=pairs_path,
            method="fusion",
            weights=weights,
        )
        
        # Evaluate
        results = evaluate_similarity(test_set, similarity_fn, top_k=top_k)
        
        logger.info(f"  P@{top_k} = {results.get('p_at_k', 0):.3f}")
        return results
    except Exception as e:
        logger.error(f"  Evaluation failed: {e}")
        return {"error": str(e)}


def run_ablation_study(
    test_set_path: Path,
    embeddings_path: Path,
    pairs_path: Path,
    visual_weights: list[float],
    top_k: int = 10,
) -> dict[str, Any]:
    """Run ablation study with different visual embedding weights."""
    logger.info("=" * 60)
    logger.info("Visual Embeddings Ablation Study")
    logger.info("=" * 60)
    logger.info("")
    
    results = {}
    
    for visual_weight in visual_weights:
        weight_key = f"visual_{visual_weight:.2f}"
        results[weight_key] = evaluate_with_visual_weight(
            test_set_path=test_set_path,
            embeddings_path=embeddings_path,
            pairs_path=pairs_path,
            visual_weight=visual_weight,
            top_k=top_k,
        )
        logger.info("")
    
    # Find best weight
    best_p_at_k = -1.0
    best_weight = None
    
    for weight_key, result in results.items():
        p_at_k = result.get("p_at_k", 0.0)
        if p_at_k > best_p_at_k:
            best_p_at_k = p_at_k
            best_weight = weight_key
    
    logger.info("=" * 60)
    logger.info("Ablation Study Results")
    logger.info("=" * 60)
    logger.info("")
    logger.info(f"{'Visual Weight':<15} {'P@{top_k}':<12} {'NDCG@{top_k}':<12} {'MRR':<12}")
    logger.info("-" * 60)
    
    for weight_key in sorted(results.keys(), key=lambda k: float(k.split("_")[1])):
        result = results[weight_key]
        visual_weight = weight_key.split("_")[1]
        p_at_k = result.get("p_at_k", 0.0)
        ndcg = result.get("ndcg", 0.0)
        mrr = result.get("mrr", 0.0)
        marker = " ← BEST" if weight_key == best_weight else ""
        logger.info(f"{visual_weight:<15} {p_at_k:<12.4f} {ndcg:<12.4f} {mrr:<12.4f}{marker}")
    
    logger.info("")
    logger.info(f"Best visual weight: {best_weight} (P@{top_k} = {best_p_at_k:.4f})")
    
    return {
        "results": results,
        "best_weight": best_weight,
        "best_p_at_k": best_p_at_k,
    }


def main() -> int:
    """Main ablation study script."""
    parser = argparse.ArgumentParser(
        description="Run ablation study for visual embeddings"
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        required=True,
        help="Path to test set JSON file",
    )
    parser.add_argument(
        "--embeddings",
        type=Path,
        required=True,
        help="Path to embeddings file",
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        required=True,
        help="Path to pairs CSV file",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top K for evaluation (default: 10)",
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs="+",
        default=[0.0, 0.10, 0.20, 0.30, 0.40],
        help="Visual embedding weights to test (default: 0.0 0.10 0.20 0.30 0.40)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to save ablation results JSON",
    )
    
    args = parser.parse_args()
    
    # Run ablation study
    results = run_ablation_study(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        visual_weights=args.weights,
        top_k=args.top_k,
    )
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\nResults saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

