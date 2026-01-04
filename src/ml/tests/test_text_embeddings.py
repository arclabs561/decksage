#!/usr/bin/env python3
"""
Tests for text embeddings integration.
"""

from __future__ import annotations

import pytest

try:
    from ml.similarity.text_embeddings import CardTextEmbedder, get_text_embedder
    from ml.similarity.fusion_integration import (
        normalize_weights,
        compute_fusion_with_text,
        get_default_weights_with_text,
    )
    TEXT_EMBEDDINGS_AVAILABLE = True
except ImportError:
    TEXT_EMBEDDINGS_AVAILABLE = False
    pytestmark = pytest.mark.skip("sentence-transformers not installed")


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_text_embedder_initialization():
    """Test that embedder can be initialized."""
    embedder = CardTextEmbedder()
    assert embedder is not None
    assert embedder.model is not None


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_card_to_text():
    """Test card dict to text conversion."""
    embedder = CardTextEmbedder()

    card = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "oracle_text": "Deal 3 damage to any target.",
    }

    text = embedder._card_to_text(card)
    assert "Lightning Bolt" in text
    assert "Instant" in text
    assert "Deal 3 damage" in text


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_embed_card():
    """Test embedding a card."""
    embedder = CardTextEmbedder()

    card = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "oracle_text": "Deal 3 damage to any target.",
    }

    embedding = embedder.embed_card(card)
    assert embedding is not None
    assert len(embedding.shape) == 1
    assert embedding.shape[0] > 0


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_similarity():
    """Test similarity between two cards."""
    embedder = CardTextEmbedder()

    card1 = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "oracle_text": "Deal 3 damage to any target.",
    }

    card2 = {
        "name": "Shock",
        "type_line": "Instant",
        "oracle_text": "Deal 2 damage to any target.",
    }

    similarity = embedder.similarity(card1, card2)
    assert 0.0 <= similarity <= 1.0
    # Similar cards should have high similarity
    assert similarity > 0.5


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_normalize_weights():
    """Test weight normalization."""
    weights = {"a": 0.2, "b": 0.3, "c": 0.5}
    normalized = normalize_weights(weights)

    assert sum(normalized.values()) == pytest.approx(1.0)
    assert normalized["a"] == 0.2
    assert normalized["b"] == 0.3
    assert normalized["c"] == 0.5


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_fusion_with_text():
    """Test fusion computation with text embeddings."""
    similarities = {
        "embed": 0.5,
        "jaccard": 0.6,
        "functional": 0.7,
    }

    weights = get_default_weights_with_text()

    card1 = {"name": "Lightning Bolt", "oracle_text": "Deal 3 damage."}
    card2 = {"name": "Shock", "oracle_text": "Deal 2 damage."}

    fused = compute_fusion_with_text(
        similarities,
        weights,
        card1=card1,
        card2=card2,
    )

    assert 0.0 <= fused <= 1.0
    # Should be weighted combination
    assert fused > 0.0


@pytest.mark.skipif(not TEXT_EMBEDDINGS_AVAILABLE, reason="Text embeddings not available")
def test_global_embedder():
    """Test global embedder singleton."""
    embedder1 = get_text_embedder()
    embedder2 = get_text_embedder()

    # Should be same instance
    assert embedder1 is embedder2
