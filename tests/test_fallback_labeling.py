#!/usr/bin/env python3
"""
Tests for fallback labeling system.

Tests:
- Co-occurrence similarity
- Embedding similarity
- Method-aware thresholds
- Name matching
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

try:
    from gensim.models import KeyedVectors
    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    pytestmark = pytest.mark.skip("Missing gensim")


def test_jaccard_similarity():
    """Test Jaccard similarity calculation."""
    from ml.scripts.fallback_labeling import jaccard_similarity
    
    set1 = {"Card1", "Card2", "Card3"}
    set2 = {"Card2", "Card3", "Card4"}
    
    sim = jaccard_similarity(set1, set2)
    
    # Intersection: {Card2, Card3} = 2
    # Union: {Card1, Card2, Card3, Card4} = 4
    # Jaccard: 2/4 = 0.5
    assert abs(sim - 0.5) < 0.01
    
    # Empty sets
    assert jaccard_similarity(set(), set()) == 0.0
    assert jaccard_similarity(set1, set()) == 0.0


def test_categorize_similarity():
    """Test similarity categorization with method-aware thresholds."""
    from ml.scripts.fallback_labeling import categorize_similarity
    
    # Co-occurrence (higher thresholds)
    assert categorize_similarity(0.25, "cooccurrence") == "highly_relevant"
    assert categorize_similarity(0.15, "cooccurrence") == "relevant"
    assert categorize_similarity(0.05, "cooccurrence") == "somewhat_relevant"
    assert categorize_similarity(0.01, "cooccurrence") == "marginally_relevant"
    
    # Embeddings (lower thresholds)
    assert categorize_similarity(0.5, "embedding") == "highly_relevant"
    assert categorize_similarity(0.3, "embedding") == "relevant"
    assert categorize_similarity(0.15, "embedding") == "somewhat_relevant"


def test_normalize_name():
    """Test name normalization."""
    from ml.scripts.fallback_labeling import normalize_name
    
    assert normalize_name("Lightning Bolt") == "lightning bolt"
    assert normalize_name("Lightning-Bolt") == "lightningbolt"
    assert normalize_name("  Lightning  Bolt  ") == "lightning bolt"
    assert normalize_name("Lightning.Bolt") == "lightningbolt"


def test_get_similar_by_cooccurrence():
    """Test finding similar cards by co-occurrence."""
    from ml.scripts.fallback_labeling import get_similar_by_cooccurrence
    
    cooccurrence = {
        "Lightning Bolt": {"Shock", "Bolt", "Fire"},
        "Shock": {"Lightning Bolt", "Bolt"},
        "Bolt": {"Lightning Bolt", "Shock"},
    }
    
    similar = get_similar_by_cooccurrence("Lightning Bolt", cooccurrence, top_k=2)
    
    assert len(similar) > 0
    # Should find Shock and Bolt as similar
    similar_names = [name for name, _ in similar]
    assert "Shock" in similar_names or "Bolt" in similar_names


@pytest.mark.skipif(not HAS_GENSIM, reason="Requires gensim")
def test_get_similar_by_embeddings():
    """Test finding similar cards by embeddings."""
    from ml.scripts.fallback_labeling import get_similar_by_embeddings
    
    # Create minimal test embeddings
    with tempfile.TemporaryDirectory() as tmpdir:
        from gensim.models import Word2Vec
        
        # Train minimal model
        sentences = [
            ["Lightning", "Bolt"],
            ["Shock", "Bolt"],
            ["Fire", "Bolt"],
        ]
        model = Word2Vec(sentences, vector_size=10, window=2, min_count=1, epochs=1)
        wv = model.wv
        
        similar = get_similar_by_embeddings("Lightning", wv, top_k=2)
        
        assert len(similar) > 0
        # Should find similar words
        similar_names = [name for name, _ in similar]
        assert len(similar_names) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

