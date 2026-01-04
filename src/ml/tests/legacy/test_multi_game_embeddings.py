#!/usr/bin/env python3
"""
Tests for multi-game embedding training.

Tests:
- Multi-game data loading
- Game detection
- Unified embedding training
- Cross-game similarity
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

try:
    import pandas as pd
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    pytestmark = pytest.mark.skip("Missing dependencies")


def test_load_multi_game_pairs():
    """Test loading pairs from multiple games."""
    from ml.scripts.train_multi_game_embeddings import load_multi_game_pairs
    
    # Create test data
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test pairs for different games
        mtg_pairs = tmp_path / "mtg_pairs.csv"
        yugioh_pairs = tmp_path / "yugioh_pairs.csv"
        
        # MTG pairs
        pd.DataFrame({
            "NAME_1": ["Lightning Bolt", "Brainstorm", "Sol Ring"],
            "NAME_2": ["Shock", "Ponder", "Mana Crypt"],
            "COUNT_SET": [10, 8, 5],
            "COUNT_MULTISET": [15, 12, 7],
        }).to_csv(mtg_pairs, index=False)
        
        # Yugioh pairs
        pd.DataFrame({
            "NAME_1": ["Dark Magician", "Blue-Eyes White Dragon"],
            "NAME_2": ["Dark Magician Girl", "Blue-Eyes Alternative"],
            "COUNT_SET": [5, 3],
            "COUNT_MULTISET": [7, 4],
        }).to_csv(yugioh_pairs, index=False)
        
        pairs_csvs = {
            "MTG": mtg_pairs,
            "YUGIOH": yugioh_pairs,
        }
        
        adj, weights, game_map = load_multi_game_pairs(pairs_csvs)
        
        # Check adjacency list
        assert "Lightning Bolt" in adj
        assert "Dark Magician" in adj
        assert len(adj) > 0
        
        # Check weights
        assert len(weights) > 0
        
        # Check game map
        assert "Lightning Bolt" in game_map
        assert "Dark Magician" in game_map


def test_infer_game_from_card_name():
    """Test game inference from card names."""
    from ml.scripts.train_multi_game_embeddings import infer_game_from_card_name
    
    # MTG cards
    assert infer_game_from_card_name("Lightning Bolt") == "MTG"
    assert infer_game_from_card_name("Brainstorm") == "MTG"
    
    # Yugioh cards
    assert infer_game_from_card_name("Dark Magician") == "YUGIOH"
    assert infer_game_from_card_name("Blue-Eyes White Dragon") == "YUGIOH"
    
    # Pokemon (if supported)
    # assert infer_game_from_card_name("Pikachu") == "POKEMON"


def test_multi_game_embedding_training():
    """Test training embeddings on multi-game data."""
    from ml.scripts.train_multi_game_embeddings import train_unified_embeddings
    
    # Create minimal test data
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test pairs
        pairs_file = tmp_path / "test_pairs.csv"
        pd.DataFrame({
            "NAME_1": ["Card1", "Card2", "Card3"],
            "NAME_2": ["Card2", "Card3", "Card1"],
            "COUNT_SET": [2, 2, 2],
            "COUNT_MULTISET": [3, 3, 3],
        }).to_csv(pairs_file, index=False)
        
        output_file = tmp_path / "test_embeddings.wv"
        
        # Train with minimal config
        wv = train_unified_embeddings(
            pairs_file,
            output_file,
            dim=10,  # Small for testing
            walk_length=5,
            num_walks=2,
            p=1.0,
            q=1.0,
        )
        
        # Check embeddings exist
        assert wv is not None
        assert len(wv.key_to_index) > 0
        
        # Check all cards have embeddings
        assert "Card1" in wv
        assert "Card2" in wv
        assert "Card3" in wv


def test_cross_game_similarity():
    """Test that embeddings can find similarities across games."""
    # This would test if cards from different games can be compared
    # using unified embeddings
    pass  # TODO: Implement when cross-game similarity is needed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

