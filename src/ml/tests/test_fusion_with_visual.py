#!/usr/bin/env python3
"""
Tests for fusion system with visual embeddings integration.
"""

from __future__ import annotations

import pytest

try:
    from ml.similarity.fusion import FusionWeights, WeightedLateFusion
    from ml.similarity.visual_embeddings import CardVisualEmbedder
    from PIL import Image

    VISUAL_EMBEDDINGS_AVAILABLE = True
except ImportError:
    VISUAL_EMBEDDINGS_AVAILABLE = False
    pytestmark = pytest.mark.skip("Visual embeddings not available")


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_fusion_weights_with_visual():
    """Test FusionWeights includes visual_embed."""
    weights = FusionWeights()
    assert hasattr(weights, "visual_embed")
    assert weights.visual_embed == 0.20  # Default weight

    # Test normalization includes visual_embed
    normalized = weights.normalized()
    total = (
        normalized.embed
        + normalized.jaccard
        + normalized.functional
        + normalized.text_embed
        + normalized.visual_embed
        + normalized.gnn
    )
    assert abs(total - 1.0) < 1e-6  # Should sum to 1.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_fusion_with_visual_embedder():
    """Test WeightedLateFusion accepts visual_embedder."""
    visual_embedder = CardVisualEmbedder()

    fusion = WeightedLateFusion(
        embeddings=None,
        adj=None,
        tagger=None,
        weights=FusionWeights(visual_embed=0.5),  # High weight for visual
        visual_embedder=visual_embedder,
    )

    assert fusion.visual_embedder is not None
    assert fusion.visual_embedder is visual_embedder


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_get_visual_embedding_similarity():
    """Test visual embedding similarity computation."""
    visual_embedder = CardVisualEmbedder()

    # Create test images
    img1 = Image.new("RGB", (224, 224), color="red")
    img2 = Image.new("RGB", (224, 224), color="red")

    # Create card data dict
    card_data = {
        "Card1": {"name": "Card1", "image_url": "test1"},
        "Card2": {"name": "Card2", "image_url": "test2"},
    }

    fusion = WeightedLateFusion(
        embeddings=None,
        adj=None,
        tagger=None,
        weights=FusionWeights(visual_embed=1.0),
        visual_embedder=visual_embedder,
        card_data=card_data,
    )

    # Test similarity computation (will use PIL images directly)
    # Note: This tests the method exists and handles inputs correctly
    similarity = fusion._get_visual_embedding_similarity("Card1", "Card2")
    # Should return 0.0 when cards not in card_data or images unavailable
    assert 0.0 <= similarity <= 1.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_fusion_without_visual_embedder():
    """Test fusion works without visual embedder (backward compatibility)."""
    fusion = WeightedLateFusion(
        embeddings=None,
        adj=None,
        tagger=None,
        weights=FusionWeights(visual_embed=0.0),  # Zero weight
        visual_embedder=None,  # No visual embedder
    )

    # Should return 0.0 when visual embedder is None
    similarity = fusion._get_visual_embedding_similarity("Card1", "Card2")
    assert similarity == 0.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_aggregate_weighted_with_visual():
    """Test weighted aggregation includes visual_embed."""
    weights = FusionWeights(visual_embed=0.5)
    fusion = WeightedLateFusion(
        embeddings=None,
        adj=None,
        tagger=None,
        weights=weights,
    )

    scores = {
        "embed": 0.5,
        "jaccard": 0.6,
        "visual_embed": 0.8,  # High visual similarity
    }

    result = fusion._aggregate_weighted(scores)
    assert 0.0 <= result <= 1.0
    # Visual should contribute to result
    assert result > 0.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_aggregate_rrf_with_visual():
    """Test RRF aggregation includes visual_embed."""
    weights = FusionWeights(visual_embed=0.5)
    fusion = WeightedLateFusion(
        embeddings=None,
        adj=None,
        tagger=None,
        weights=weights,
    )

    ranks = {
        "embed": 1,
        "jaccard": 2,
        "visual_embed": 1,  # Rank 1
    }

    result = fusion._aggregate_rrf(ranks)
    assert result > 0.0
    # Higher weight + lower rank = higher contribution
    assert result > 0.0

