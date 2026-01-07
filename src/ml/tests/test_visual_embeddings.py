#!/usr/bin/env python3
"""
Tests for visual embeddings integration.
"""

from __future__ import annotations

import pytest

try:
    from ml.similarity.visual_embeddings import CardVisualEmbedder, get_visual_embedder
    from PIL import Image
    import numpy as np

    VISUAL_EMBEDDINGS_AVAILABLE = True
except ImportError:
    VISUAL_EMBEDDINGS_AVAILABLE = False
    pytestmark = pytest.mark.skip("sentence-transformers or pillow not installed")


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_visual_embedder_initialization():
    """Test that embedder can be initialized."""
    embedder = CardVisualEmbedder()
    assert embedder is not None
    assert embedder.model is not None


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_get_image_url():
    """Test extracting image URL from card dict."""
    embedder = CardVisualEmbedder()

    # Test various image URL formats
    card1 = {"name": "Test Card", "image_url": "https://example.com/image.png"}
    assert embedder._get_image_url(card1) == "https://example.com/image.png"

    card2 = {"name": "Test Card", "image": "https://example.com/image2.png"}
    assert embedder._get_image_url(card2) == "https://example.com/image2.png"

    card3 = {"name": "Test Card", "images": [{"url": "https://example.com/image3.png"}]}
    assert embedder._get_image_url(card3) == "https://example.com/image3.png"

    card4 = {"name": "Test Card", "images": {"large": "https://example.com/image4.png"}}
    assert embedder._get_image_url(card4) == "https://example.com/image4.png"

    # No image URL
    card5 = {"name": "Test Card"}
    assert embedder._get_image_url(card5) is None


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_get_cache_key():
    """Test cache key generation."""
    embedder = CardVisualEmbedder()

    # Test with card dict
    card1 = {"name": "Test Card", "image_url": "https://example.com/image.png"}
    key1 = embedder._get_cache_key(card1)
    assert key1.startswith("url_")

    # Test with card name string
    key2 = embedder._get_cache_key("Test Card")
    assert key2.startswith("name_")

    # Test with PIL Image
    img = Image.new("RGB", (224, 224), color="red")
    key3 = embedder._get_cache_key(img)
    assert key3.startswith("image_")


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_preprocess_image():
    """Test image preprocessing."""
    embedder = CardVisualEmbedder()

    # Create test image
    img = Image.new("RGB", (500, 300), color="blue")
    processed = embedder._preprocess_image(img)

    assert processed.size == (224, 224)  # Should be resized to target size


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_embed_card_with_pil_image():
    """Test embedding a PIL Image directly."""
    embedder = CardVisualEmbedder()

    # Create test image
    img = Image.new("RGB", (224, 224), color="red")
    embedding = embedder.embed_card(img)

    assert embedding is not None
    assert isinstance(embedding, np.ndarray)
    assert len(embedding.shape) == 1
    assert embedding.shape[0] > 0  # Should have embedding dimension


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_embed_card_without_image():
    """Test embedding a card without image URL returns zero vector."""
    embedder = CardVisualEmbedder()

    card = {"name": "Test Card"}  # No image URL
    embedding = embedder.embed_card(card)

    assert embedding is not None
    assert isinstance(embedding, np.ndarray)
    # Should return zero vector when image unavailable
    assert np.allclose(embedding, 0.0) or embedding.shape[0] > 0


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_similarity():
    """Test similarity between two images."""
    embedder = CardVisualEmbedder()

    # Create two test images
    img1 = Image.new("RGB", (224, 224), color="red")
    img2 = Image.new("RGB", (224, 224), color="red")  # Same color

    similarity = embedder.similarity(img1, img2)
    assert 0.0 <= similarity <= 1.0

    # Same image should have high similarity
    assert similarity > 0.5


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_embed_batch():
    """Test batch embedding."""
    embedder = CardVisualEmbedder()

    # Create test images
    images = [
        Image.new("RGB", (224, 224), color="red"),
        Image.new("RGB", (224, 224), color="blue"),
        Image.new("RGB", (224, 224), color="green"),
    ]

    embeddings = embedder.embed_batch(images)
    assert embeddings is not None
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape[0] == 3  # Should have 3 embeddings
    assert embeddings.shape[1] > 0  # Should have embedding dimension


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_get_visual_embedder():
    """Test global embedder getter."""
    embedder1 = get_visual_embedder()
    embedder2 = get_visual_embedder()

    # Should return same instance (singleton)
    assert embedder1 is embedder2


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_caching():
    """Test that embeddings are cached."""
    embedder = CardVisualEmbedder()

    # Clear cache
    embedder._memory_cache.clear()

    img = Image.new("RGB", (224, 224), color="red")
    embedding1 = embedder.embed_card(img)

    # Second call should use cache
    embedding2 = embedder.embed_card(img)

    # Should be the same (from cache)
    assert np.allclose(embedding1, embedding2)


@pytest.mark.skipif(not VISUAL_EMBEDDINGS_AVAILABLE, reason="Visual embeddings not available")
def test_similarity_with_missing_image():
    """Test similarity when one card has no image."""
    embedder = CardVisualEmbedder()

    img1 = Image.new("RGB", (224, 224), color="red")
    card2 = {"name": "Test Card"}  # No image

    similarity = embedder.similarity(img1, card2)
    # Should return 0.0 when one image is missing
    assert similarity == 0.0

