#!/usr/bin/env python3
"""
Filtered visual embeddings evaluation - only tests queries with image coverage.

This ensures both query cards and their relevant matches have images,
giving a true measure of visual embedding impact.
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


def filter_test_set_with_images(
    test_set_path: Path,
    image_urls: dict[str, str],
) -> dict[str, Any]:
    """
    Filter test set to only include queries where query and relevant cards have images.
    
    Args:
        test_set_path: Path to test set JSON
        image_urls: Dict mapping card names to image URLs
    
    Returns:
        Filtered test set dict
    """
    logger.info(f"Loading test set from {test_set_path}...")
    with open(test_set_path) as f:
        test_data = json.load(f)
    
    queries = test_data.get("queries", test_data)
    logger.info(f"  Original queries: {len(queries)}")
    
    # Filter queries
    filtered_queries = {}
    for query, labels in queries.items():
        # Check if query card has image
        if query not in image_urls:
            continue
        
        # Check if at least one relevant card has image
        has_relevant_with_image = False
        filtered_labels = {}
        
        if isinstance(labels, dict):
            for level, cards in labels.items():
                if level == "irrelevant":
                    filtered_labels[level] = cards
                    continue
                
                # Filter to only cards with images
                cards_with_images = [c for c in cards if c in image_urls]
                if cards_with_images:
                    has_relevant_with_image = True
                    filtered_labels[level] = cards_with_images
                else:
                    filtered_labels[level] = []
        elif isinstance(labels, list):
            cards_with_images = [c for c in labels if c in image_urls]
            if cards_with_images:
                has_relevant_with_image = True
                filtered_labels = {
                    "highly_relevant": cards_with_images,
                    "relevant": [],
                    "somewhat_relevant": [],
                    "marginally_relevant": [],
                    "irrelevant": [],
                }
        
        if has_relevant_with_image:
            filtered_queries[query] = filtered_labels
    
    logger.info(f"  Filtered queries: {len(filtered_queries)} ({len(filtered_queries)/len(queries)*100:.1f}% coverage)")
    
    return {"queries": filtered_queries}


def evaluate_fusion(
    test_set_path: Path,
    embeddings_path: Path,
    pairs_path: Path,
    image_urls_path: Path,
    use_visual: bool = True,
    top_k: int = 10,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """Evaluate fusion with or without visual embeddings on filtered test set."""
    logger.info(f"Evaluating fusion (visual={'enabled' if use_visual else 'disabled'})...")
    
    try:
        from gensim.models import KeyedVectors
        from ml.similarity.fusion import WeightedLateFusion, FusionWeights
        from ml.similarity.similarity_methods import load_graph
        from ml.utils.evaluation import compute_precision_at_k
        
        # Load image URLs
        logger.info(f"Loading image URLs from {image_urls_path}...")
        with open(image_urls_path) as f:
            image_urls = json.load(f)
        logger.info(f"  Loaded {len(image_urls)} image URLs")
        
        # Filter test set
        filtered_test_set = filter_test_set_with_images(test_set_path, image_urls)
        queries = filtered_test_set["queries"]
        
        if not queries:
            logger.warning("  No queries with image coverage!")
            return {"error": "No queries with image coverage", "p_at_k": 0.0}
        
        # Load embeddings
        logger.info(f"Loading embeddings from {embeddings_path}...")
        embeddings = KeyedVectors.load(str(embeddings_path))
        logger.info(f"  Loaded {len(embeddings)} embeddings")
        
        # Load graph
        logger.info(f"Loading graph from {pairs_path}...")
        adj, _ = load_graph(csv_path=str(pairs_path), filter_lands=True)
        logger.info(f"  Loaded graph with {len(adj)} cards")
        
        # Load card data with image URLs
        card_data = {}
        for card_name, image_url in image_urls.items():
            card_data[card_name] = {
                "name": card_name,
                "image_url": image_url,
            }
        logger.info(f"  Created card data for {len(card_data)} cards")
        
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
            tagger=None,
            weights=weights,
            text_embedder=None,
            visual_embedder=visual_embedder,
            card_data=card_data,
        )
        
        # Sample queries if requested
        if sample_size and len(queries) > sample_size:
            import random
            query_items = list(queries.items())
            random.seed(42)
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
                predictions = fusion.similar(query, top_k)
                if not predictions:
                    skipped += 1
                    continue
                
                pred_cards = [card for card, _ in predictions]
                
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
                
                p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=top_k)
                scores.append(p_at_k)
                evaluated += 1
                
                if evaluated % 10 == 0:
                    logger.info(f"  Evaluated {evaluated}/{len(queries)} queries...")
                    
            except Exception as e:
                skipped += 1
                if evaluated < 5:
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
            "filtered_queries": len(queries),
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
        description="Filtered visual embeddings evaluation"
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
        "--image-urls",
        type=Path,
        default=Path("data/processed/card_attributes_enriched_image_urls.json"),
        help="Path to image URLs JSON file",
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
        default=Path("experiments/visual_embeddings_evaluation_filtered.json"),
        help="Path to save results JSON",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Visual Embeddings Evaluation (Filtered)")
    logger.info("=" * 60)
    logger.info("")
    
    # Evaluate with visual embeddings
    results_with = evaluate_fusion(
        test_set_path=args.test_set,
        embeddings_path=args.embeddings,
        pairs_path=args.pairs,
        image_urls_path=args.image_urls,
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
        image_urls_path=args.image_urls,
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

