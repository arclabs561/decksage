#!/usr/bin/env python3
"""
Validation script for visual embeddings integration.

Quick validation that visual embeddings are working correctly:
1. Can initialize embedder
2. Can generate embeddings
3. Fusion integration works
4. API state includes visual embedder
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

import logging
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def validate_imports() -> tuple[bool, str]:
    """Validate all required imports are available."""
    logger.info("Validating imports...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder, get_visual_embedder
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from ml.api.api import get_state, ApiState
        logger.info("  ✓ All imports successful")
        return True, "All imports successful"
    except ImportError as e:
        logger.error(f"  ✗ Import failed: {e}")
        return False, f"Import failed: {e}"


def validate_embedder_initialization() -> tuple[bool, str]:
    """Validate visual embedder can be initialized."""
    logger.info("Validating embedder initialization...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        
        embedder = CardVisualEmbedder()
        assert embedder is not None
        assert embedder.model is not None
        logger.info("  ✓ Embedder initialized successfully")
        return True, "Embedder initialized"
    except ImportError:
        return False, "Dependencies not installed (sentence-transformers, pillow)"
    except Exception as e:
        logger.error(f"  ✗ Initialization failed: {e}")
        return False, f"Initialization failed: {e}"


def validate_embedding_generation() -> tuple[bool, str]:
    """Validate embeddings can be generated."""
    logger.info("Validating embedding generation...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from PIL import Image
        
        embedder = CardVisualEmbedder()
        
        # Test with PIL Image
        img = Image.new("RGB", (224, 224), color="red")
        embedding = embedder.embed_card(img)
        
        assert embedding is not None
        assert len(embedding.shape) == 1
        assert embedding.shape[0] > 0
        
        logger.info(f"  ✓ Embedding generated, shape: {embedding.shape}")
        return True, f"Embedding shape: {embedding.shape}"
    except Exception as e:
        logger.error(f"  ✗ Embedding generation failed: {e}")
        return False, f"Embedding generation failed: {e}"


def validate_fusion_integration() -> tuple[bool, str]:
    """Validate fusion system integration."""
    logger.info("Validating fusion integration...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from unittest.mock import MagicMock
        
        visual_embedder = CardVisualEmbedder()
        
        # Create fusion with visual embeddings
        fusion = WeightedLateFusion(
            embeddings=MagicMock(),
            adj={"Card1": {"Card2"}},
            tagger=None,
            weights=FusionWeights(visual_embed=0.5),
            visual_embedder=visual_embedder,
            card_data={},
        )
        
        assert fusion.visual_embedder is not None
        assert fusion.weights.visual_embed == 0.5
        
        # Test similarity computation (should return 0.0 for missing cards)
        similarity = fusion._get_visual_embedding_similarity("Card1", "Card2")
        assert 0.0 <= similarity <= 1.0
        
        logger.info("  ✓ Fusion integration successful")
        return True, "Fusion integration works"
    except Exception as e:
        logger.error(f"  ✗ Fusion integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Fusion integration failed: {e}"


def validate_api_state() -> tuple[bool, str]:
    """Validate API state includes visual embedder."""
    logger.info("Validating API state...")
    
    try:
        from ml.api.api import get_state, ApiState
        
        state = get_state()
        assert hasattr(state, "visual_embedder")
        
        logger.info("  ✓ API state includes visual_embedder field")
        return True, "API state correct"
    except Exception as e:
        logger.error(f"  ✗ API state validation failed: {e}")
        return False, f"API state validation failed: {e}"


def validate_fusion_weights() -> tuple[bool, str]:
    """Validate fusion weights include visual_embed."""
    logger.info("Validating fusion weights...")
    
    try:
        from ml.similarity.fusion import FusionWeights
        
        weights = FusionWeights()
        assert hasattr(weights, "visual_embed")
        assert weights.visual_embed == 0.20  # Default
        
        normalized = weights.normalized()
        total = (
            normalized.embed
            + normalized.jaccard
            + normalized.functional
            + normalized.text_embed
            + normalized.visual_embed
            + normalized.gnn
        )
        assert abs(total - 1.0) < 0.01
        
        logger.info(f"  ✓ Fusion weights include visual_embed: {normalized.visual_embed:.2%}")
        return True, f"Visual embed weight: {normalized.visual_embed:.2%}"
    except Exception as e:
        logger.error(f"  ✗ Fusion weights validation failed: {e}")
        return False, f"Fusion weights validation failed: {e}"


def validate_error_handling() -> tuple[bool, str]:
    """Validate error handling for missing images."""
    logger.info("Validating error handling...")
    
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
        
        embedder = CardVisualEmbedder()
        
        # Test with missing image URL
        card1 = {"name": "Card1"}  # No image URL
        card2 = {"name": "Card2", "image_url": "https://example.com/card2.png"}
        
        similarity = embedder.similarity(card1, card2)
        assert similarity == 0.0
        
        logger.info("  ✓ Error handling works (missing images return 0.0)")
        return True, "Error handling works"
    except Exception as e:
        logger.error(f"  ✗ Error handling validation failed: {e}")
        return False, f"Error handling validation failed: {e}"


def main() -> int:
    """Run all validation checks."""
    logger.info("=" * 60)
    logger.info("Visual Embeddings Validation")
    logger.info("=" * 60)
    logger.info("")
    
    validations = [
        ("Imports", validate_imports),
        ("Embedder Initialization", validate_embedder_initialization),
        ("Embedding Generation", validate_embedding_generation),
        ("Fusion Integration", validate_fusion_integration),
        ("API State", validate_api_state),
        ("Fusion Weights", validate_fusion_weights),
        ("Error Handling", validate_error_handling),
    ]
    
    results: dict[str, tuple[bool, str]] = {}
    
    for name, validator in validations:
        try:
            success, message = validator()
            results[name] = (success, message)
        except Exception as e:
            logger.error(f"  ✗ {name} validation crashed: {e}")
            results[name] = (False, f"Crashed: {e}")
        logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Validation Summary")
    logger.info("=" * 60)
    
    passed = 0
    total = 0
    
    for name, (success, message) in results.items():
        total += 1
        if success:
            passed += 1
            status = "✓"
        else:
            status = "✗"
        logger.info(f"{status} {name}: {message}")
    
    logger.info("")
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("")
        logger.info("✅ All validations passed! Visual embeddings are working correctly.")
        return 0
    else:
        logger.info("")
        logger.warning(f"⚠️  {total - passed} validation(s) failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

