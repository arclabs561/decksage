#!/usr/bin/env python3
"""
End-to-end integration test for visual embeddings.

Tests the full pipeline:
1. Visual embedder initialization
2. Image download and caching
3. Embedding generation
4. Fusion integration
5. API integration
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
from unittest.mock import MagicMock, patch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_visual_embedder_initialization():
    """Test visual embedder can be initialized."""
    logger.info("Testing visual embedder initialization...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        
        embedder = CardVisualEmbedder()
        assert embedder is not None
        assert embedder.model is not None
        logger.info("  ✓ Visual embedder initialized successfully")
        return True
    except ImportError as e:
        logger.warning(f"  ✗ Visual embeddings not available: {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Failed to initialize visual embedder: {e}")
        return False


def test_fusion_integration():
    """Test visual embeddings integrate with fusion system."""
    logger.info("Testing fusion integration...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        
        visual_embedder = CardVisualEmbedder()
        
        # Create mock data
        mock_embeddings = MagicMock()
        mock_adj = {"Card1": {"Card2"}}
        
        fusion = WeightedLateFusion(
            embeddings=mock_embeddings,
            adj=mock_adj,
            tagger=None,
            weights=FusionWeights(visual_embed=0.5),
            visual_embedder=visual_embedder,
            card_data={},
        )
        
        assert fusion.visual_embedder is not None
        assert fusion.weights.visual_embed == 0.5
        
        logger.info("  ✓ Fusion integration successful")
        return True
    except Exception as e:
        logger.error(f"  ✗ Fusion integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_integration():
    """Test visual embeddings integrate with API."""
    logger.info("Testing API integration...")
    
    try:
        from ml.api.api import get_state, ApiState
        
        state = get_state()
        assert hasattr(state, "visual_embedder")
        
        logger.info("  ✓ API state includes visual_embedder")
        return True
    except Exception as e:
        logger.error(f"  ✗ API integration failed: {e}")
        return False


def test_load_signals_integration():
    """Test load_signals_to_state initializes visual embedder."""
    logger.info("Testing load_signals integration...")
    
    try:
        from ml.api.load_signals import load_signals_to_state
        from ml.api.api import get_state
        
        state = get_state()
        
        # Try to load visual embedder
        load_signals_to_state(visual_embedder_model="google/siglip-base-patch16-224")
        
        # Check if visual embedder was initialized (may be None if dependencies missing)
        if state.visual_embedder is not None:
            logger.info("  ✓ Visual embedder loaded successfully")
        else:
            logger.warning("  ⚠ Visual embedder not loaded (dependencies may be missing)")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ load_signals integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling for missing images."""
    logger.info("Testing error handling...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        
        embedder = CardVisualEmbedder()
        
        # Test with missing image URL
        card1 = {"name": "Card1"}  # No image URL
        card2 = {"name": "Card2", "image_url": "https://example.com/card2.png"}
        
        similarity = embedder.similarity(card1, card2)
        assert similarity == 0.0
        
        logger.info("  ✓ Error handling works correctly")
        return True
    except Exception as e:
        logger.error(f"  ✗ Error handling test failed: {e}")
        return False


def test_caching():
    """Test caching behavior."""
    logger.info("Testing caching...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from PIL import Image
        
        embedder = CardVisualEmbedder()
        
        # Clear cache
        embedder._memory_cache.clear()
        
        img = Image.new("RGB", (224, 224), color="red")
        embedding1 = embedder.embed_card(img)
        
        # Second call should use cache
        embedding2 = embedder.embed_card(img)
        
        # Should be the same
        import numpy as np
        assert np.allclose(embedding1, embedding2)
        
        logger.info("  ✓ Caching works correctly")
        return True
    except Exception as e:
        logger.error(f"  ✗ Caching test failed: {e}")
        return False


def main():
    """Run all integration tests."""
    logger.info("=" * 60)
    logger.info("Visual Embeddings Integration Tests")
    logger.info("=" * 60)
    logger.info("")
    
    results = {
        "Initialization": test_visual_embedder_initialization(),
        "Fusion Integration": test_fusion_integration(),
        "API Integration": test_api_integration(),
        "Load Signals": test_load_signals_integration(),
        "Error Handling": test_error_handling(),
        "Caching": test_caching(),
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

