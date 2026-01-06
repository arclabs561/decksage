#!/usr/bin/env python3
"""
Simple visual embeddings evaluation that actually generates results.

This script:
1. Loads test set
2. Evaluates with and without visual embeddings
3. Generates comparison results
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

import json
import logging
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def evaluate_fusion(
    test_set_path: Path,
    embeddings_path: Path,
    pairs_path: Path,
    use_visual: bool = True,
    top_k: int = 10,
    sample_size: int | None = 50,  # Sample for faster evaluation
) -> dict[str, Any]:
    """Evaluate fusion with or without visual embeddings."""
    logger.info(f"Evaluating fusion (visual={'enabled' if use_visual else 'disabled'})...")
    
    try:
        from gensim.models import KeyedVectors
        from ml.similarity.fusion import WeightedLateFusion, FusionWeights
        from ml.similarity.similarity_methods import load_graph
        from ml.utils.evaluation import compute_precision_at_k
        
        # Load embeddings
        logger.info(f"Loading embeddings from {embeddings_path}...")
        embeddings = KeyedVectors.load(str(embeddings_path))
        logger.info(f"  Loaded {len(embeddings)} embeddings")
        
        # Load graph
        logger.info(f"Loading graph from {pairs_path}...")
        adj, _ = load_graph(csv_path=str(pairs_path), filter_lands=True)
        logger.info(f"  Loaded graph with {len(adj)} cards")
        
        # Load card data with image URLs
        card_data = None
        try:
            import pandas as pd
            from ml.utils.paths import PATHS
            # Try to load card data with images
            card_attrs_path = PATHS.card_attributes
            # Check for image URL mapping JSON first (faster)
            image_urls_path = card_attrs_path.parent / f"{card_attrs_path.stem}_image_urls.json"
            if image_urls_path.exists():
                with open(image_urls_path) as f:
                    image_urls = json.load(f)
                # Load card attributes and add image URLs
                df = pd.read_csv(card_attrs_path, nrows=50000)
                card_data = {}
                for _, row in df.iterrows():
                    name = str(row["name"])
                    card_data[name] = {
                        "name": name,
                        "oracle_text": str(row.get("oracle_text", "")),
                        "type_line": str(row.get("type", "")),
                        "image_url": image_urls.get(name, ""),  # Add image URL
                    }
                logger.info(f"  Loaded {len(card_data)} cards with {sum(1 for c in card_data.values() if c.get('image_url'))} image URLs")
            else:
                logger.warning(f"  Image URL mapping not found: {image_urls_path}")
        except Exception as e:
            logger.warning(f"  Could not load card data: {e}")
        
        # Load visual embedder if needed
        visual_embedder = None
        if use_visual:
            try:
                from ml.similarity.visual_embeddings import get_visual_embedder
                visual_embedder = get_visual_embedder()
                logger.info("  Visual embedder loaded")
            except Exception as e:
                logger.warning(f"  Could not load visual embedder: {e}")
                use_visual = False
        
        # Create fusion weights
        if use_visual:
            weights = FusionWeights(
                embed=0.20,
                jaccard=0.15,
                functional=0.10,
                text_embed=0.25,
                visual_embed=0.20,
                gnn=0.10,
            ).normalized()
        else:
            weights = FusionWeights(
                embed=0.25,
                jaccard=0.20,
                functional=0.15,
                text_embed=0.30,
                visual_embed=0.0,
                gnn=0.10,
            ).normalized()
        
        # Create fusion
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            tagger=None,  # Disable for speed
            weights=weights,
            text_embedder=None,  # Disable for speed
            visual_embedder=visual_embedder,
            card_data=card_data,  # Pass card data with image URLs
        )
        
        # Load test set
        logger.info(f"Loading test set from {test_set_path}...")
        with open(test_set_path) as f:
            test_data = json.load(f)
        
        queries = test_data.get("queries", test_data)
        logger.info(f"  Loaded {len(queries)} queries")
        
        # Sample queries if requested
        if sample_size and len(queries) > sample_size:
            import random
            query_items = list(queries.items())
            random.seed(42)  # Reproducible
            sampled = random.sample(query_items, sample_size)
            queries = dict(sampled)
            logger.info(f"  Sampled {len(queries)} queries for evaluation")
        
        # Evaluate
        logger.info("Evaluating queries...")
        scores = []
        evaluated = 0
        skipped = 0
        
        for query, labels in queries.items():
            try:
                # Get predictions
                predictions = fusion.similar(query, top_k)
                if not predictions:
                    skipped += 1
                    continue
                
                # Extract card names
                pred_cards = [card for card, _ in predictions]
                
                # Convert labels to dict format
                if isinstance(labels, dict):
                    labels_dict = labels
                else:
                    labels_dict = {
                        "highly_relevant": labels if isinstance(labels, list) else [],
                        "relevant": [],
                        "somewhat_relevant": [],
                        "marginally_relevant": [],
                        "irrelevant": [],
                    }
                
                # Compute P@K
                p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=top_k)
                scores.append(p_at_k)
                evaluated += 1
                
                if evaluated % 10 == 0:
                    logger.info(f"  Evaluated {evaluated}/{len(queries)} queries...")
                    
            except Exception as e:
                skipped += 1
                if evaluated < 5:  # Only log first few errors
                    logger.debug(f"  Error evaluating '{query}': {e}")
                continue
        
        if evaluated == 0:
            logger.warning(f"  No queries evaluated (skipped: {skipped})")
            p_at_10 = 0.0
        else:
            p_at_10 = sum(scores) / len(scores)
            logger.info(f"  Evaluated {evaluated} queries, skipped {skipped}")
            logger.info(f"  Mean P@{top_k}: {p_at_10:.4f}")
        
        return {
            "p_at_k": p_at_10,
            "evaluated": evaluated,
            "skipped": skipped,
            "total_queries": len(queries),
        }
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "p_at_k": 0.0}


def main() -> int:
    """Main evaluation script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Simple visual embeddings evaluation"
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_unified_magic.json"),
        help="Path to test set JSON file",
    )
    parser.add_argument(
        "--embeddings",
        type=Path,
        default=Path("data/embeddings/multitask_enhanced_vv2024-W01.wv"),
        help="Path to embeddings file",
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        default=Path("data/processed/pairs_all_games_combined.csv"),
        help="Path to pairs CSV file",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top K for evaluation (default: 10)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of queries to sample (default: 50, use 0 for all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/visual_embeddings_evaluation_simple.json"),
        help="Path to save results JSON",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Visual Embeddings Evaluation (Simple)")
    logger.info("=" * 60)
    logger.info("")
    
    # Evaluate with visual embeddings
    results_with = evaluate_fusion(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        use_visual=True,
        top_k=args.top_k,
        sample_size=args.sample_size if args.sample_size > 0 else None,
    )
    logger.info("")
    
    # Evaluate without visual embeddings
    results_without = evaluate_fusion(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        use_visual=False,
        top_k=args.top_k,
        sample_size=args.sample_size if args.sample_size > 0 else None,
    )
    logger.info("")
    
    # Compare
    p_at_k_with = results_with.get("p_at_k", 0.0)
    p_at_k_without = results_without.get("p_at_k", 0.0)
    
    improvement = p_at_k_with - p_at_k_without
    relative_improvement = (improvement / p_at_k_without * 100) if p_at_k_without > 0 else 0.0
    
    comparison = {
        "with_visual": results_with,
        "without_visual": results_without,
        "improvement": {
            "absolute": improvement,
            "relative_percent": relative_improvement,
        },
    }
    
    logger.info("=" * 60)
    logger.info("Results")
    logger.info("=" * 60)
    logger.info(f"With visual embeddings:    P@{args.top_k} = {p_at_k_with:.4f}")
    logger.info(f"Without visual embeddings: P@{args.top_k} = {p_at_k_without:.4f}")
    logger.info(f"Improvement:               {improvement:+.4f} ({relative_improvement:+.2f}%)")
    logger.info("")
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(comparison, f, indent=2)
    logger.info(f"Results saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

