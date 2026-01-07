#!/usr/bin/env python3
"""
Optimize fusion weights including visual embeddings.

Extends existing optimization scripts to include visual embeddings in the weight search.
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


def optimize_fusion_weights_with_visual(
    embeddings_path: Path,
    pairs_path: Path,
    test_set_path: Path,
    top_k: int = 10,
    include_visual: bool = True,
) -> dict[str, Any]:
    """Optimize fusion weights including visual embeddings."""
    logger.info("Optimizing fusion weights (with visual embeddings)...")
    
    try:
        from gensim.models import KeyedVectors
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.similarity.similarity_methods import load_graph
        from ml.utils.evaluation import evaluate_similarity
        from scipy.optimize import minimize
        import numpy as np
        
        # Load data
        logger.info(f"Loading embeddings from {embeddings_path}...")
        embeddings = KeyedVectors.load(str(embeddings_path))
        
        logger.info(f"Loading graph from {pairs_path}...")
        adj, _ = load_graph(pairs_path, filter_lands=True)
        
        logger.info(f"Loading test set from {test_set_path}...")
        with open(test_set_path) as f:
            test_set = json.load(f)
        
        # Load embedders
        text_embedder = None
        visual_embedder = None
        card_data = {}
        
        try:
            from ml.similarity.text_embeddings import get_text_embedder
            text_embedder = get_text_embedder()
            logger.info("  Text embedder loaded")
        except Exception as e:
            logger.debug(f"  Text embedder not available: {e}")
        
        if include_visual:
            try:
                from ml.similarity.visual_embeddings import get_visual_embedder
                visual_embedder = get_visual_embedder()
                logger.info("  Visual embedder loaded")
                
                # Try to load card data for image URLs
                from ml.utils.paths import PATHS
                card_attrs_path = PATHS.card_attributes
                if card_attrs_path.exists():
                    import pandas as pd
                    df = pd.read_csv(card_attrs_path, nrows=50000)
                    for _, row in df.iterrows():
                        name = str(row["name"])
                        card_data[name] = {
                            "name": name,
                            "oracle_text": str(row.get("oracle_text", "")),
                            "type_line": str(row.get("type", "")),
                            "image_url": str(row.get("image_url", "")),
                        }
                    logger.info(f"  Loaded {len(card_data)} card records with image URLs")
            except Exception as e:
                logger.debug(f"  Visual embedder not available: {e}")
        
        # Optimization function
        def objective(weights_array: np.ndarray) -> float:
            """Objective: negative P@10."""
            if include_visual and visual_embedder:
                w = FusionWeights(
                    embed=float(weights_array[0]),
                    jaccard=float(weights_array[1]),
                    functional=float(weights_array[2]),
                    text_embed=float(weights_array[3]),
                    visual_embed=float(weights_array[4]),
                    gnn=float(weights_array[5]),
                )
            elif text_embedder:
                w = FusionWeights(
                    embed=float(weights_array[0]),
                    jaccard=float(weights_array[1]),
                    functional=float(weights_array[2]),
                    text_embed=float(weights_array[3]),
                    gnn=float(weights_array[4]),
                )
            else:
                w = FusionWeights(
                    embed=float(weights_array[0]),
                    jaccard=float(weights_array[1]),
                    functional=float(weights_array[2]),
                    gnn=float(weights_array[3]),
                )
            
            fusion = WeightedLateFusion(
                embeddings=embeddings,
                adj=adj,
                tagger=None,
                weights=w,
                text_embedder=text_embedder,
                visual_embedder=visual_embedder,
                card_data=card_data if card_data else None,
            )
            
            def similarity_fn(query: str, k: int) -> list[tuple[str, float]]:
                results = fusion.similar(query, k)
                return [(card, float(score)) for card, score in results]
            
            results = evaluate_similarity(test_set, similarity_fn, top_k=top_k)
            p_at_k = results.get("p_at_k", 0.0)
            return -p_at_k  # Negative for minimization
        
        # Initial guess and bounds
        if include_visual and visual_embedder:
            x0 = np.array([0.15, 0.10, 0.05, 0.20, 0.20, 0.30])  # embed, jaccard, functional, text, visual, gnn
            bounds = [(0.0, 1.0)] * 6
        elif text_embedder:
            x0 = np.array([0.20, 0.15, 0.10, 0.25, 0.30])  # embed, jaccard, functional, text, gnn
            bounds = [(0.0, 1.0)] * 5
        else:
            x0 = np.array([0.25, 0.25, 0.10, 0.40])  # embed, jaccard, functional, gnn
            bounds = [(0.0, 1.0)] * 4
        
        # Constraint: weights sum to 1
        def constraint(x):
            return np.sum(x) - 1.0
        
        constraints = {'type': 'eq', 'fun': constraint}
        
        # Optimize
        logger.info("Running optimization...")
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 50},
        )
        
        # Extract best weights
        if include_visual and visual_embedder:
            best_weights = FusionWeights(
                embed=float(result.x[0]),
                jaccard=float(result.x[1]),
                functional=float(result.x[2]),
                text_embed=float(result.x[3]),
                visual_embed=float(result.x[4]),
                gnn=float(result.x[5]),
            )
        elif text_embedder:
            best_weights = FusionWeights(
                embed=float(result.x[0]),
                jaccard=float(result.x[1]),
                functional=float(result.x[2]),
                text_embed=float(result.x[3]),
                gnn=float(result.x[4]),
            )
        else:
            best_weights = FusionWeights(
                embed=float(result.x[0]),
                jaccard=float(result.x[1]),
                functional=float(result.x[2]),
                gnn=float(result.x[3]),
            )
        
        best_p_at_k = -result.fun
        
        logger.info(f"  Best P@{top_k}: {best_p_at_k:.4f}")
        logger.info(f"  Best weights: {best_weights}")
        
        return {
            "best_weights": {
                "embed": best_weights.embed,
                "jaccard": best_weights.jaccard,
                "functional": best_weights.functional,
                "text_embed": best_weights.text_embed,
                "visual_embed": best_weights.visual_embed if include_visual else 0.0,
                "gnn": best_weights.gnn,
            },
            "best_p_at_k": best_p_at_k,
            "optimization_success": result.success,
            "message": result.message,
        }
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def main() -> int:
    """Main optimization script."""
    parser = argparse.ArgumentParser(
        description="Optimize fusion weights including visual embeddings"
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
        "--test-set",
        type=Path,
        required=True,
        help="Path to test set JSON file",
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
        required=True,
        help="Path to save optimized weights JSON",
    )
    parser.add_argument(
        "--no-visual",
        action="store_true",
        help="Disable visual embeddings (optimize without them)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Fusion Weight Optimization (with Visual Embeddings)")
    logger.info("=" * 60)
    logger.info("")
    
    results = optimize_fusion_weights_with_visual(
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        test_set_path=args.test_set,
        top_k=args.top_k,
        include_visual=not args.no_visual,
    )
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"\nResults saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

