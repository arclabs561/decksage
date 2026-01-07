#!/usr/bin/env python3
"""
Integrate Hybrid Embeddings into API

Loads and configures all three embedding types for the API.
Updates fusion system with optimal weights.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..similarity.fusion import FusionWeights, WeightedLateFusion
from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def load_hybrid_embeddings(
    gnn_model_path: Path | None = None,
    instruction_model_name: str = "intfloat/e5-base-v2",
    cooccurrence_embeddings_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load all three embedding types.

    Returns:
        Dict with embedders and metadata
    """
    result = {
        "instruction_embedder": None,
        "gnn_embedder": None,
        "cooccurrence_embeddings": None,
        "loaded": {},
    }

    # 1. Instruction-tuned embeddings (always available - zero-shot)
    try:
        logger.info("Loading instruction-tuned embeddings...")
        result["instruction_embedder"] = InstructionTunedCardEmbedder(
            model_name=instruction_model_name,
        )
        result["loaded"]["instruction"] = True
        logger.info("✓ Instruction-tuned embeddings loaded")
    except Exception as e:
        logger.warning(f"Failed to load instruction-tuned embeddings: {e}")
        result["loaded"]["instruction"] = False

    # 2. GNN embeddings
    if gnn_model_path and gnn_model_path.exists():
        try:
            logger.info("Loading GNN embeddings...")
            result["gnn_embedder"] = CardGNNEmbedder(model_path=gnn_model_path)
            result["loaded"]["gnn"] = True
            logger.info("✓ GNN embeddings loaded")
        except Exception as e:
            logger.warning(f"Failed to load GNN embeddings: {e}")
            result["loaded"]["gnn"] = False
    else:
        logger.info("GNN model not found, skipping")
        result["loaded"]["gnn"] = False

    # 3. Co-occurrence embeddings (Node2Vec)
    if cooccurrence_embeddings_path and cooccurrence_embeddings_path.exists():
        try:
            from gensim.models import KeyedVectors
            logger.info("Loading co-occurrence embeddings...")
            result["cooccurrence_embeddings"] = KeyedVectors.load(
                str(cooccurrence_embeddings_path)
            )
            result["loaded"]["cooccurrence"] = True
            logger.info("✓ Co-occurrence embeddings loaded")
        except Exception as e:
            logger.warning(f"Failed to load co-occurrence embeddings: {e}")
            result["loaded"]["cooccurrence"] = False
    else:
        logger.info("Co-occurrence embeddings not found, skipping")
        result["loaded"]["cooccurrence"] = False

    return result


def create_fusion_with_hybrid_embeddings(
    embeddings_data: dict[str, Any],
    adj: dict[str, set[str]] | None = None,
    tagger: Any | None = None,
    card_data: dict[str, dict[str, Any]] | None = None,
) -> WeightedLateFusion:
    """
    Create fusion system with all three embedding types.

    Uses recommended weights based on capabilities:
    - GNN: 30% (multi-hop, new cards)
    - Instruction-tuned: 25% (zero-shot, semantic)
    - Co-occurrence: 20% (established patterns)
    - Jaccard: 15% (direct co-occurrence)
    - Functional tags: 10% (role-based)
    """
    # Recommended weights for hybrid system
    weights = FusionWeights(
        embed=0.20,        # Co-occurrence embeddings
        jaccard=0.15,      # Direct co-occurrence
        functional=0.10,   # Functional tags
        text_embed=0.25,   # Instruction-tuned (zero-shot, new cards)
        visual_embed=0.20, # Visual embeddings (card images)
        gnn=0.30,          # GraphSAGE (multi-hop, new cards)
    )

    # Load visual embedder if available
    visual_embedder = None
    try:
        from ..similarity.visual_embeddings import get_visual_embedder
        visual_embedder = get_visual_embedder()
    except (ImportError, Exception):
        pass  # Visual embeddings optional

    fusion = WeightedLateFusion(
        embeddings=embeddings_data.get("cooccurrence_embeddings"),
        adj=adj or {},
        tagger=tagger,
        weights=weights,
        text_embedder=embeddings_data.get("instruction_embedder"),
        visual_embedder=visual_embedder,
        gnn_embedder=embeddings_data.get("gnn_embedder"),
        card_data=card_data or {},
    )

    return fusion


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Integrate hybrid embeddings into system"
    )
    parser.add_argument(
        "--gnn-model",
        type=Path,
        default=PATHS.embeddings / "gnn_graphsage.json",
        help="Path to GNN model",
    )
    parser.add_argument(
        "--cooccurrence-embeddings",
        type=Path,
        help="Path to co-occurrence embeddings (Node2Vec)",
    )
    parser.add_argument(
        "--instruction-model",
        type=str,
        default="intfloat/e5-base-instruct-v2",
        help="Instruction-tuned model name",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test the integration",
    )

    args = parser.parse_args()

    logger.info("="*60)
    logger.info("Integrating Hybrid Embeddings")
    logger.info("="*60)

    # Load all embeddings
    embeddings_data = load_hybrid_embeddings(
        gnn_model_path=args.gnn_model,
        instruction_model_name=args.instruction_model,
        cooccurrence_embeddings_path=args.cooccurrence_embeddings,
    )

    # Print summary
    logger.info("\nLoaded Embeddings:")
    for name, loaded in embeddings_data["loaded"].items():
        status = "✓" if loaded else "✗"
        logger.info(f"  {status} {name}")

    # Test if requested
    if args.test:
        logger.info("\nTesting integration...")
        fusion = create_fusion_with_hybrid_embeddings(embeddings_data)

        # Test query
        test_card = "Lightning Bolt"
        logger.info(f"\nTesting similarity for: {test_card}")

        try:
            results = fusion.find_similar(test_card, topn=5)
            logger.info("Top 5 similar cards:")
            for card, score in results:
                logger.info(f"  {card}: {score:.4f}")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return 1

    logger.info("\n✓ Integration complete")
    logger.info("\nTo use in API:")
    logger.info("  1. Load embeddings using load_hybrid_embeddings()")
    logger.info("  2. Create fusion with create_fusion_with_hybrid_embeddings()")
    logger.info("  3. Use fusion.find_similar() for recommendations")

    return 0


if __name__ == "__main__":
    exit(main())
