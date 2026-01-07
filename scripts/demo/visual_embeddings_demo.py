#!/usr/bin/env python3
"""
Interactive demo of visual embeddings functionality.

Shows how visual embeddings work in practice with real examples.
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_basic_embedding():
    """Demo basic embedding generation."""
    logger.info("=" * 60)
    logger.info("Demo 1: Basic Visual Embedding")
    logger.info("=" * 60)
    
    try:
        from ml.similarity.visual_embeddings import get_visual_embedder
        from PIL import Image
        
        embedder = get_visual_embedder()
        
        # Create test images
        img1 = Image.new("RGB", (224, 224), color="red")
        img2 = Image.new("RGB", (224, 224), color="blue")
        
        # Generate embeddings
        emb1 = embedder.embed_card(img1)
        emb2 = embedder.embed_card(img2)
        
        logger.info(f"  Image 1 embedding shape: {emb1.shape}")
        logger.info(f"  Image 2 embedding shape: {emb2.shape}")
        
        # Compute similarity
        similarity = embedder.similarity(img1, img2)
        logger.info(f"  Similarity (red vs blue): {similarity:.3f}")
        
        # Same image should have high similarity
        similarity_same = embedder.similarity(img1, img1)
        logger.info(f"  Similarity (red vs red): {similarity_same:.3f}")
        
        logger.info("  ✓ Basic embedding demo complete")
        return True
    except Exception as e:
        logger.error(f"  ✗ Demo failed: {e}")
        return False


def demo_fusion_integration():
    """Demo fusion system with visual embeddings."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Demo 2: Fusion Integration")
    logger.info("=" * 60)
    
    try:
        from ml.similarity.visual_embeddings import get_visual_embedder
        from ml.similarity.fusion import FusionWeights, WeightedLateFusion
        from unittest.mock import MagicMock
        
        visual_embedder = get_visual_embedder()
        
        # Create mock data
        mock_embeddings = MagicMock()
        mock_adj = {
            "Lightning Bolt": {"Shock", "Chain Lightning"},
            "Shock": {"Lightning Bolt", "Bolt"},
        }
        
        # Create fusion with visual embeddings
        weights = FusionWeights(
            embed=0.20,
            jaccard=0.15,
            functional=0.10,
            text_embed=0.25,
            visual_embed=0.20,  # Visual embeddings
            gnn=0.30,
        )
        
        fusion = WeightedLateFusion(
            embeddings=mock_embeddings,
            adj=mock_adj,
            tagger=None,
            weights=weights,
            visual_embedder=visual_embedder,
            card_data={
                "Lightning Bolt": {"name": "Lightning Bolt", "image_url": "test1"},
                "Shock": {"name": "Shock", "image_url": "test2"},
            },
        )
        
        logger.info(f"  Fusion weights (normalized):")
        normalized = weights.normalized()
        logger.info(f"    Visual embeddings: {normalized.visual_embed:.2%}")
        logger.info(f"    Text embeddings: {normalized.text_embed:.2%}")
        logger.info(f"    GNN: {normalized.gnn:.2%}")
        
        # Test similarity computation
        similarity = fusion._get_visual_embedding_similarity("Lightning Bolt", "Shock")
        logger.info(f"  Visual similarity (Lightning Bolt vs Shock): {similarity:.3f}")
        
        logger.info("  ✓ Fusion integration demo complete")
        return True
    except Exception as e:
        logger.error(f"  ✗ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_batch_processing():
    """Demo batch processing."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Demo 3: Batch Processing")
    logger.info("=" * 60)
    
    try:
        from ml.similarity.visual_embeddings import get_visual_embedder
        from PIL import Image
        
        embedder = get_visual_embedder()
        
        # Create batch of images
        images = [
            Image.new("RGB", (224, 224), color="red"),
            Image.new("RGB", (224, 224), color="green"),
            Image.new("RGB", (224, 224), color="blue"),
        ]
        
        # Batch embed
        embeddings = embedder.embed_batch(images)
        
        logger.info(f"  Processed {len(images)} images")
        logger.info(f"  Embeddings shape: {embeddings.shape}")
        
        # Compute pairwise similarities
        logger.info("  Pairwise similarities:")
        for i in range(len(images)):
            for j in range(i + 1, len(images)):
                sim = embedder.similarity(images[i], images[j])
                logger.info(f"    Image {i+1} vs Image {j+1}: {sim:.3f}")
        
        logger.info("  ✓ Batch processing demo complete")
        return True
    except Exception as e:
        logger.error(f"  ✗ Demo failed: {e}")
        return False


def demo_error_handling():
    """Demo error handling."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Demo 4: Error Handling")
    logger.info("=" * 60)
    
    try:
        from ml.similarity.visual_embeddings import get_visual_embedder
        
        embedder = get_visual_embedder()
        
        # Test with missing image URL
        card1 = {"name": "Card1"}  # No image URL
        card2 = {"name": "Card2", "image_url": "https://example.com/card2.png"}
        
        similarity = embedder.similarity(card1, card2)
        logger.info(f"  Missing image URL handling: {similarity:.3f} (should be 0.0)")
        
        # Test with invalid URL (will fail gracefully)
        card3 = {"name": "Card3", "image_url": "https://invalid-url-that-does-not-exist.com/image.png"}
        similarity2 = embedder.similarity(card3, card3)
        logger.info(f"  Invalid URL handling: {similarity2:.3f} (gracefully handled)")
        
        logger.info("  ✓ Error handling demo complete")
        return True
    except Exception as e:
        logger.error(f"  ✗ Demo failed: {e}")
        return False


def main() -> int:
    """Run all demos."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Visual Embeddings Interactive Demo")
    logger.info("=" * 60)
    logger.info("")
    logger.info("This demo shows visual embeddings in action.")
    logger.info("Note: Some demos use placeholder images (expected).")
    logger.info("")
    
    results = {
        "Basic Embedding": demo_basic_embedding(),
        "Fusion Integration": demo_fusion_integration(),
        "Batch Processing": demo_batch_processing(),
        "Error Handling": demo_error_handling(),
    }
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Demo Summary")
    logger.info("=" * 60)
    
    passed = 0
    total = 0
    
    for name, success in results.items():
        total += 1
        if success:
            passed += 1
            status = "✓"
        else:
            status = "✗"
        logger.info(f"{status} {name}")
    
    logger.info("")
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("")
        logger.info("✅ All demos completed successfully!")
        logger.info("")
        logger.info("Visual embeddings are working correctly.")
        logger.info("To use in production:")
        logger.info("  1. Set VISUAL_EMBEDDER_MODEL environment variable")
        logger.info("  2. Ensure cards have image URLs")
        logger.info("  3. Use fusion method in API")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

