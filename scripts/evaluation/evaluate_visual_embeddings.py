#!/usr/bin/env python3
"""
Evaluate visual embeddings impact on similarity search.

Compares fusion with and without visual embeddings to measure improvement.
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


def evaluate_with_visual_embeddings(
    test_set_path: Path,
    embeddings_path: Path | None = None,
    pairs_path: Path | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate fusion with visual embeddings enabled."""
    logger.info("Evaluating with visual embeddings...")
    
    try:
        from ml.evaluation.similarity_helper import create_similarity_function
        from ml.utils.evaluation import evaluate_similarity
        
        # Load test set
        with open(test_set_path) as f:
            test_set = json.load(f)
        
        # Create similarity function with visual embeddings
        similarity_fn = create_similarity_function(
            embeddings_path=str(embeddings_path) if embeddings_path else None,
            pairs_path=str(pairs_path) if pairs_path else None,
            method="fusion",
        )
        
        # Evaluate
        results = evaluate_similarity(test_set, similarity_fn, top_k=top_k)
        
        logger.info(f"  ✓ Evaluation complete: P@{top_k} = {results.get('p_at_k', 0):.3f}")
        return results
    except Exception as e:
        logger.error(f"  ✗ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def evaluate_without_visual_embeddings(
    test_set_path: Path,
    embeddings_path: Path | None = None,
    pairs_path: Path | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate fusion with visual embeddings disabled."""
    logger.info("Evaluating without visual embeddings...")
    
    try:
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.evaluation.similarity_helper import create_similarity_function
        from ml.utils.evaluation import evaluate_similarity
        from gensim.models import KeyedVectors
        import json
        
        # Load embeddings
        if embeddings_path:
            embeddings = KeyedVectors.load(str(embeddings_path))
        else:
            raise ValueError("embeddings_path required")
        
        # Load graph using proper function
        adj = {}
        if pairs_path and pairs_path.exists():
            from ml.similarity.similarity_methods import load_graph
            adj, _ = load_graph(csv_path=str(pairs_path), filter_lands=True)
        
        # Create fusion WITHOUT visual embeddings
        weights = FusionWeights(visual_embed=0.0).normalized()
        
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            tagger=None,
            weights=weights,
            visual_embedder=None,  # Disabled
        )
        
        def similarity_fn(query: str, k: int) -> list[tuple[str, float]]:
            results = fusion.similar(query, k)
            return [(card, float(score)) for card, score in results]
        
        # Load test set
        with open(test_set_path) as f:
            test_set = json.load(f)
        
        # Evaluate
        results = evaluate_similarity(test_set, similarity_fn, top_k=top_k)
        
        logger.info(f"  ✓ Evaluation complete: P@{top_k} = {results.get('p_at_k', 0):.3f}")
        return results
    except Exception as e:
        logger.error(f"  ✗ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def compare_results(
    with_visual: dict[str, Any],
    without_visual: dict[str, Any],
) -> dict[str, Any]:
    """Compare results with and without visual embeddings."""
    logger.info("Comparing results...")
    
    p_at_k_with = with_visual.get("p_at_k", 0.0)
    p_at_k_without = without_visual.get("p_at_k", 0.0)
    
    improvement = p_at_k_with - p_at_k_without
    relative_improvement = (improvement / p_at_k_without * 100) if p_at_k_without > 0 else 0.0
    
    comparison = {
        "with_visual": {
            "p_at_k": p_at_k_with,
            "ndcg": with_visual.get("ndcg", 0.0),
            "mrr": with_visual.get("mrr", 0.0),
        },
        "without_visual": {
            "p_at_k": p_at_k_without,
            "ndcg": without_visual.get("ndcg", 0.0),
            "mrr": without_visual.get("mrr", 0.0),
        },
        "improvement": {
            "absolute": improvement,
            "relative_percent": relative_improvement,
        },
    }
    
    logger.info(f"  P@{10} improvement: {improvement:+.4f} ({relative_improvement:+.2f}%)")
    
    return comparison


def main() -> int:
    """Main evaluation script."""
    parser = argparse.ArgumentParser(
        description="Evaluate visual embeddings impact on similarity search"
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
        help="Path to embeddings file",
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        help="Path to pairs CSV file",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top K for evaluation (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to save comparison results JSON",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Visual Embeddings Evaluation")
    logger.info("=" * 60)
    logger.info("")
    
    # Evaluate with visual embeddings
    results_with = evaluate_with_visual_embeddings(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        top_k=args.top_k,
    )
    logger.info("")
    
    # Evaluate without visual embeddings
    results_without = evaluate_without_visual_embeddings(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        top_k=args.top_k,
    )
    logger.info("")
    
    # Compare
    comparison = compare_results(results_with, results_without)
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(comparison, f, indent=2)
        logger.info(f"Results saved to {args.output}")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Evaluation Complete")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

