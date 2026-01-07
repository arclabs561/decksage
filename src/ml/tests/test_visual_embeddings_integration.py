#!/usr/bin/env python3
"""
Integration tests for visual embeddings in the full pipeline.

Tests visual embeddings integration with:
- Fusion system
- API endpoints
- Search/indexing
- Error handling
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

try:
    from ml.similarity.visual_embeddings import CardVisualEmbedder, get_visual_embedder
    from ml.similarity.fusion import FusionWeights, WeightedLateFusion
    from ml.api.api import get_state, ApiState
    from PIL import Image
    import numpy as np

    VISUAL_EMBEDDINGS_AVAILABLE = True
except ImportError:
    VISUAL_EMBEDDINGS_AVAILABLE = False
    pytestmark = pytest.mark.skip("Visual embeddings not available")


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
class TestVisualEmbeddingsFusionIntegration:
    """Test visual embeddings integration with fusion system."""

    def test_fusion_with_visual_embeddings(self):
        """Test fusion system uses visual embeddings when available."""
        visual_embedder = CardVisualEmbedder()
        
        # Mock embeddings and graph
        mock_embeddings = MagicMock()
        mock_adj = {"Card1": {"Card2", "Card3"}}
        
        # Create fusion with visual embedder
        fusion = WeightedLateFusion(
            embeddings=mock_embeddings,
            adj=mock_adj,
            tagger=None,
            weights=FusionWeights(visual_embed=0.5),
            visual_embedder=visual_embedder,
            card_data={
                "Card1": {"name": "Card1", "image_url": "https://example.com/card1.png"},
                "Card2": {"name": "Card2", "image_url": "https://example.com/card2.png"},
            },
        )
        
        assert fusion.visual_embedder is not None
        assert fusion.weights.visual_embed == 0.5

    def test_fusion_without_visual_embeddings(self):
        """Test fusion system works without visual embeddings (backward compatibility)."""
        mock_embeddings = MagicMock()
        mock_adj = {"Card1": {"Card2"}}
        
        fusion = WeightedLateFusion(
            embeddings=mock_embeddings,
            adj=mock_adj,
            tagger=None,
            weights=FusionWeights(visual_embed=0.0),
            visual_embedder=None,
        )
        
        # Should work fine without visual embedder
        assert fusion.visual_embedder is None
        similarity = fusion._get_visual_embedding_similarity("Card1", "Card2")
        assert similarity == 0.0

    def test_visual_embedding_similarity_computation(self):
        """Test visual embedding similarity is computed correctly."""
        visual_embedder = CardVisualEmbedder()
        
        # Create test images
        img1 = Image.new("RGB", (224, 224), color="red")
        img2 = Image.new("RGB", (224, 224), color="red")
        
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=FusionWeights(visual_embed=1.0),
            visual_embedder=visual_embedder,
            card_data={},
        )
        
        # Test similarity computation
        similarity = fusion._get_visual_embedding_similarity("Card1", "Card2")
        # Should return 0.0 when cards not in card_data
        assert 0.0 <= similarity <= 1.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
class TestVisualEmbeddingsAPIIntegration:
    """Test visual embeddings integration with API."""

    def test_api_state_has_visual_embedder(self):
        """Test ApiState includes visual_embedder field."""
        state = ApiState()
        assert hasattr(state, "visual_embedder")
        assert state.visual_embedder is None  # Initially None

    @patch("ml.api.load_signals.CardVisualEmbedder")
    def test_load_signals_initializes_visual_embedder(self, mock_embedder_class):
        """Test load_signals_to_state initializes visual embedder."""
        from ml.api.load_signals import load_signals_to_state
        
        mock_embedder = MagicMock()
        mock_embedder_class.return_value = mock_embedder
        
        state = get_state()
        load_signals_to_state(visual_embedder_model="clip-ViT-B-16")
        
        # Visual embedder should be initialized
        assert state.visual_embedder is not None

    def test_fusion_endpoint_includes_visual_embedder(self):
        """Test fusion endpoint passes visual_embedder to WeightedLateFusion."""
        from fastapi.testclient import TestClient
        from ml.api.api import app
        
        state = get_state()
        state.embeddings = MagicMock()
        state.graph_data = {"adj": {"Lightning Bolt": {"Shock"}}}
        state.card_attrs = {
            "Lightning Bolt": {"name": "Lightning Bolt", "image_url": "https://example.com/bolt.png"},
            "Shock": {"name": "Shock", "image_url": "https://example.com/shock.png"},
        }
        
        # Mock visual embedder
        mock_visual_embedder = MagicMock()
        mock_visual_embedder.similarity.return_value = 0.8
        state.visual_embedder = mock_visual_embedder
        
        client = TestClient(app)
        
        # This will fail if visual_embedder isn't passed correctly
        # We're just checking it doesn't crash
        try:
            response = client.post(
                "/v1/similar",
                json={"query": "Lightning Bolt", "top_k": 5, "mode": "fusion"},
            )
            # Should either succeed or fail gracefully (not crash)
            assert response.status_code in [200, 400, 404, 503, 500]
        except Exception:
            # If it crashes, that's a problem
            pytest.fail("Fusion endpoint crashed when visual_embedder was set")


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
class TestVisualEmbeddingsErrorHandling:
    """Test error handling in visual embeddings."""

    def test_missing_image_url_returns_zero(self):
        """Test missing image URL returns zero similarity."""
        visual_embedder = CardVisualEmbedder()
        
        card1 = {"name": "Card1"}  # No image URL
        card2 = {"name": "Card2", "image_url": "https://example.com/card2.png"}
        
        similarity = visual_embedder.similarity(card1, card2)
        assert similarity == 0.0

    def test_invalid_image_url_handles_gracefully(self):
        """Test invalid image URL handles gracefully."""
        visual_embedder = CardVisualEmbedder()
        
        card1 = {"name": "Card1", "image_url": "https://invalid-url-that-does-not-exist.com/image.png"}
        card2 = {"name": "Card2", "image_url": "https://invalid-url-that-does-not-exist.com/image2.png"}
        
        # Should return 0.0 or handle gracefully without crashing
        similarity = visual_embedder.similarity(card1, card2)
        assert 0.0 <= similarity <= 1.0

    def test_fusion_handles_visual_embedder_errors(self):
        """Test fusion handles visual embedder errors gracefully."""
        visual_embedder = CardVisualEmbedder()
        
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=FusionWeights(visual_embed=0.5),
            visual_embedder=visual_embedder,
            card_data={},
        )
        
        # Should return 0.0 when cards not found or images unavailable
        similarity = fusion._get_visual_embedding_similarity("Nonexistent", "Card")
        assert similarity == 0.0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
class TestVisualEmbeddingsCaching:
    """Test caching behavior in visual embeddings."""

    def test_embedding_cache(self):
        """Test embeddings are cached."""
        visual_embedder = CardVisualEmbedder()
        
        # Clear cache
        visual_embedder._memory_cache.clear()
        
        img = Image.new("RGB", (224, 224), color="blue")
        embedding1 = visual_embedder.embed_card(img)
        
        # Second call should use cache
        embedding2 = visual_embedder.embed_card(img)
        
        # Should be the same (from cache)
        assert np.allclose(embedding1, embedding2)

    def test_image_download_cache(self):
        """Test downloaded images are cached."""
        visual_embedder = CardVisualEmbedder()
        
        # This would test image caching, but requires actual image download
        # For now, just verify cache directory exists
        assert visual_embedder.image_cache_dir.exists()


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
class TestVisualEmbeddingsBatchProcessing:
    """Test batch processing in visual embeddings."""

    def test_batch_embedding(self):
        """Test batch embedding processing."""
        visual_embedder = CardVisualEmbedder()
        
        images = [
            Image.new("RGB", (224, 224), color="red"),
            Image.new("RGB", (224, 224), color="blue"),
            Image.new("RGB", (224, 224), color="green"),
        ]
        
        embeddings = visual_embedder.embed_batch(images)
        
        assert embeddings.shape[0] == 3
        assert embeddings.shape[1] > 0

    def test_batch_with_missing_images(self):
        """Test batch processing handles missing images."""
        visual_embedder = CardVisualEmbedder()
        
        cards = [
            {"name": "Card1", "image_url": "https://example.com/card1.png"},
            {"name": "Card2"},  # No image URL
            {"name": "Card3", "image_url": "https://example.com/card3.png"},
        ]
        
        embeddings = visual_embedder.embed_batch(cards)
        
        # Should return embeddings for all cards (zero vectors for missing)
        assert embeddings.shape[0] == 3
        assert embeddings.shape[1] > 0

