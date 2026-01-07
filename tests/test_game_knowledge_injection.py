"""Tests for game knowledge injection system."""

import json
from pathlib import Path

import pytest

from ml.knowledge import GameKnowledgeBase, retrieve_game_knowledge
from ml.knowledge.models import GameKnowledge


@pytest.fixture
def knowledge_base(tmp_path: Path) -> GameKnowledgeBase:
    """Create knowledge base with test data."""
    kb_dir = tmp_path / "game_knowledge"
    kb_dir.mkdir()
    
    # Create minimal test knowledge
    test_knowledge = {
        "game": "magic",
        "mechanics": {
            "mana_system": "Test mana system",
            "color_system": "Test colors",
            "card_types": ["Creature", "Instant"],
            "keywords": ["Flash", "Haste"],
            "special_rules": "Test rules",
            "terminology": {"CMC": "Converted Mana Cost"}
        },
        "archetypes": [
            {
                "name": "Burn",
                "description": "Aggressive red deck",
                "strategy": "Deal damage fast",
                "core_cards": ["Lightning Bolt"],
                "flex_slots": ["Goblin Guide"],
                "key_features": ["Fast", "Linear"],
                "typical_curve": "Low",
                "interaction_level": "Light",
                "meta_position": "Tier 1"
            }
        ],
        "formats": [
            {
                "name": "Modern",
                "legal_sets": ["All sets from 8th Edition"],
                "rotation_schedule": "No rotation",
                "ban_list": ["Birthing Pod"],
                "restricted_list": [],
                "meta_context": "Diverse format",
                "last_updated": "2025-01-01"
            }
        ],
        "examples": [
            {
                "query": "Lightning Bolt",
                "card1": "Lightning Bolt",
                "card2": "Chain Lightning",
                "score": 0.92,
                "reasoning": "Both are 1-mana red burn",
                "format": "Legacy"
            }
        ],
        "temporal_context": {},
        "last_updated": "2025-01-01T00:00:00"
    }
    
    with open(kb_dir / "magic.json", "w") as f:
        json.dump(test_knowledge, f)
    
    return GameKnowledgeBase(knowledge_dir=kb_dir)


def test_load_game_knowledge(knowledge_base: GameKnowledgeBase):
    """Test loading game knowledge."""
    knowledge = knowledge_base.load_game_knowledge("magic")
    assert knowledge is not None
    assert knowledge.game == "magic"
    assert knowledge.mechanics.mana_system == "Test mana system"
    assert len(knowledge.archetypes) == 1
    assert knowledge.archetypes[0].name == "Burn"


def test_load_nonexistent_game(knowledge_base: GameKnowledgeBase):
    """Test loading nonexistent game returns None."""
    knowledge = knowledge_base.load_game_knowledge("nonexistent")
    assert knowledge is None


def test_retrieve_relevant_knowledge(knowledge_base: GameKnowledgeBase):
    """Test retrieving relevant knowledge chunks."""
    result = knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="Lightning Bolt",
        format="Modern",
        archetype="Burn",
        top_k=5,
    )
    
    assert "mechanics" in result
    assert "archetypes" in result
    assert "formats" in result
    assert "examples" in result
    assert len(result["examples"]) > 0


def test_retrieve_knowledge_with_format_filter(knowledge_base: GameKnowledgeBase):
    """Test format filtering in knowledge retrieval."""
    result = knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="test",
        format="Modern",
        top_k=3,
    )
    
    # Should include format-specific knowledge
    assert "formats" in result
    # Format content should mention Modern
    assert "Modern" in result["formats"] or result["formats"] == ""


def test_retrieve_knowledge_with_archetype_filter(knowledge_base: GameKnowledgeBase):
    """Test archetype filtering in knowledge retrieval."""
    result = knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="test",
        archetype="Burn",
        top_k=3,
    )
    
    # Should include archetype-specific knowledge
    assert "archetypes" in result
    # Archetype content should mention Burn
    assert "Burn" in result["archetypes"] or result["archetypes"] == ""


def test_retrieve_game_knowledge_convenience_function(knowledge_base: GameKnowledgeBase, monkeypatch):
    """Test convenience function for knowledge retrieval."""
    # Mock the GameKnowledgeBase to use our test instance
    from ml import knowledge as kb_module
    
    def mock_kb():
        return knowledge_base
    
    monkeypatch.setattr(kb_module, "GameKnowledgeBase", lambda *args, **kwargs: knowledge_base)
    
    result = retrieve_game_knowledge(
        game="magic",
        query="Lightning Bolt",
        format="Modern",
    )
    
    assert "mechanics" in result
    assert "examples" in result


def test_knowledge_chunking(knowledge_base: GameKnowledgeBase):
    """Test that knowledge is properly chunked."""
    knowledge = knowledge_base.load_game_knowledge("magic")
    assert knowledge is not None
    
    chunks = knowledge_base._chunk_knowledge(knowledge)
    
    # Should have at least mechanics, archetype, and format chunks
    assert len(chunks) >= 3
    
    # Check chunk structure
    mechanics_chunk = next((c for c in chunks if c.category == "mechanics"), None)
    assert mechanics_chunk is not None
    assert mechanics_chunk.game == "magic"
    assert "Test mana system" in mechanics_chunk.content
    
    archetype_chunk = next((c for c in chunks if c.category == "archetype"), None)
    assert archetype_chunk is not None
    assert "Burn" in archetype_chunk.content


def test_knowledge_caching(knowledge_base: GameKnowledgeBase):
    """Test that knowledge is cached after first load."""
    # First load
    knowledge1 = knowledge_base.load_game_knowledge("magic")
    assert knowledge1 is not None
    
    # Second load should use cache
    knowledge2 = knowledge_base.load_game_knowledge("magic")
    assert knowledge2 is knowledge1  # Same object from cache


def test_empty_knowledge_handling(knowledge_base: GameKnowledgeBase):
    """Test handling when game knowledge doesn't exist."""
    result = knowledge_base.retrieve_relevant_knowledge(
        game="nonexistent",
        query="test",
        top_k=5,
    )
    
    # Should return empty structure, not crash
    assert result["mechanics"] == ""
    assert result["archetypes"] == ""
    assert result["formats"] == ""
    assert result["examples"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

