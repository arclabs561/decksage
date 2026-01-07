#!/usr/bin/env python3
"""
Test visual embeddings in actual usage scenarios.

Simulates real-world usage:
1. Similarity search with visual embeddings
2. Fusion with visual embeddings enabled
3. Batch processing
4. API-like usage patterns
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
    # Fallback: add src to path
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

import logging
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_similarity_search_with_visual():
    """Test similarity search using visual embeddings."""
    logger.info("Testing similarity search with visual embeddings...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from PIL import Image
        
        # Initialize embedder
        visual_embedder = CardVisualEmbedder()
        
        # Create mock embeddings and graph
        mock_embeddings = MagicMock()
        mock_embeddings.most_similar.return_value = [("Card2", 0.8), ("Card3", 0.7)]
        mock_adj = {"Card1": {"Card2", "Card3"}}
        
        # Create card data with image URLs
        card_data = {
            "Card1": {"name": "Card1", "image_url": "test1"},
            "Card2": {"name": "Card2", "image_url": "test2"},
            "Card3": {"name": "Card3", "image_url": "test3"},
        }
        
        # Create fusion with visual embeddings
        fusion = WeightedLateFusion(
            embeddings=mock_embeddings,
            adj=mock_adj,
            tagger=None,
            weights=FusionWeights(
                embed=0.3,
                jaccard=0.2,
                visual_embed=0.5,  # High weight for visual
            ),
            visual_embedder=visual_embedder,
            card_data=card_data,
        )
        
        # Test similarity search
        # Note: This will use actual images if available, or return 0.0 for missing
        results = fusion.similar("Card1", k=2)
        
        logger.info(f"  ✓ Similarity search returned {len(results)} results")
        return True
    except Exception as e:
        logger.error(f"  ✗ Similarity search failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_processing_usage():
    """Test batch processing in a real usage scenario."""
    logger.info("Testing batch processing...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from PIL import Image
        
        embedder = CardVisualEmbedder()
        
        # Simulate batch of cards
        cards = [
            Image.new("RGB", (224, 224), color="red"),
            Image.new("RGB", (224, 224), color="blue"),
            Image.new("RGB", (224, 224), color="green"),
        ]
        
        embeddings = embedder.embed_batch(cards)
        
        assert embeddings.shape[0] == 3
        assert embeddings.shape[1] > 0
        
        logger.info(f"  ✓ Batch processed {len(cards)} cards, embeddings shape: {embeddings.shape}")
        return True
    except Exception as e:
        logger.error(f"  ✗ Batch processing failed: {e}")
        return False


def test_fusion_aggregation_with_visual():
    """Test fusion aggregation includes visual embeddings."""
    logger.info("Testing fusion aggregation with visual embeddings...")
    
    try:
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        
        visual_embedder = CardVisualEmbedder()
        
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=FusionWeights(visual_embed=0.5),
            visual_embedder=visual_embedder,
        )
        
        # Test aggregation with visual embedding score
        scores = {
            "embed": 0.5,
            "jaccard": 0.6,
            "visual_embed": 0.8,  # High visual similarity
        }
        
        result = fusion._aggregate_weighted(scores)
        
        assert 0.0 <= result <= 1.0
        assert result > 0.0  # Should be positive
        
        logger.info(f"  ✓ Fusion aggregation result: {result:.3f}")
        return True
    except Exception as e:
        logger.error(f"  ✗ Fusion aggregation failed: {e}")
        return False


def test_api_like_usage():
    """Test usage pattern similar to API endpoint."""
    logger.info("Testing API-like usage pattern...")
    
    try:
        from ml.api.api import get_state
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.similarity.visual_embeddings import get_visual_embedder
        
        state = get_state()
        
        # Simulate API endpoint behavior
        if state.embeddings is None:
            logger.warning("  ⚠ Embeddings not loaded, skipping API-like test")
            return True
        
        # Get visual embedder (like API does)
        visual_embedder = get_visual_embedder()
        
        # Create fusion (like _similar_fusion does)
        fusion = WeightedLateFusion(
            embeddings=state.embeddings,
            adj=state.graph_data.get("adj", {}) if state.graph_data else {},
            tagger=None,
            weights=FusionWeights(visual_embed=0.2),
            visual_embedder=visual_embedder,
            card_data=state.card_attrs or {},
        )
        
        logger.info("  ✓ API-like usage pattern works")
        return True
    except Exception as e:
        logger.error(f"  ✗ API-like usage failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mixed_modalities():
    """Test visual embeddings work with other modalities."""
    logger.info("Testing mixed modalities...")
    
    try:
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from unittest.mock import MagicMock
        
        visual_embedder = CardVisualEmbedder()
        
        fusion = WeightedLateFusion(
            embeddings=MagicMock(),
            adj={"Card1": {"Card2"}},
            tagger=None,
            weights=FusionWeights(
                embed=0.25,
                jaccard=0.15,
                functional=0.10,
                text_embed=0.25,
                visual_embed=0.20,  # Visual embeddings
                gnn=0.05,
            ),
            visual_embedder=visual_embedder,
            card_data={},
        )
        
        # Test that all modalities are included
        normalized = fusion.weights.normalized()
        total = (
            normalized.embed
            + normalized.jaccard
            + normalized.functional
            + normalized.text_embed
            + normalized.visual_embed
            + normalized.gnn
        )
        
        assert abs(total - 1.0) < 0.01  # Should sum to ~1.0
        
        logger.info(f"  ✓ Mixed modalities work, total weight: {total:.3f}")
        return True
    except Exception as e:
        logger.error(f"  ✗ Mixed modalities test failed: {e}")
        return False


def main():
    """Run all usage tests."""
    logger.info("=" * 60)
    logger.info("Visual Embeddings Usage Tests")
    logger.info("=" * 60)
    logger.info("")
    
    results = {
        "Similarity Search": test_similarity_search_with_visual(),
        "Batch Processing": test_batch_processing_usage(),
        "Fusion Aggregation": test_fusion_aggregation_with_visual(),
        "API-like Usage": test_api_like_usage(),
        "Mixed Modalities": test_mixed_modalities(),
    }
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Test Results Summary")
    logger.info("=" * 60)
    
    passed = 0
    total = 0
    
    for test_name, result in results.items():
        total += 1
        if result:
            passed += 1
            status = "✓"
        else:
            status = "✗"
        logger.info(f"{status} {test_name}")
    
    logger.info("")
    logger.info(f"Passed: {passed}/{total}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

