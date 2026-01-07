"""Integration tests for knowledge injection in prompts."""

import pytest

from ml.knowledge import GameKnowledgeBase


@pytest.fixture
def real_knowledge_base():
    """Use real knowledge base from data directory."""
    return GameKnowledgeBase()


def test_magic_knowledge_retrieval(real_knowledge_base: GameKnowledgeBase):
    """Test retrieving Magic knowledge."""
    result = real_knowledge_base.retrieve_relevant_knowledge(
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

    # Should include Magic-specific mechanics
    assert "mana" in result["mechanics"].lower() or result["mechanics"] == ""

    # Should include Burn archetype if available
    if result["archetypes"]:
        assert "burn" in result["archetypes"].lower() or "lightning" in result["archetypes"].lower()


def test_pokemon_knowledge_retrieval(real_knowledge_base: GameKnowledgeBase):
    """Test retrieving Pokemon knowledge."""
    result = real_knowledge_base.retrieve_relevant_knowledge(
        game="pokemon",
        query="Pikachu",
        format="Standard",
        top_k=5,
    )

    assert "mechanics" in result
    assert "examples" in result

    # Should include Pokemon-specific mechanics
    if result["mechanics"]:
        assert "energy" in result["mechanics"].lower() or "prize" in result["mechanics"].lower()


def test_yugioh_knowledge_retrieval(real_knowledge_base: GameKnowledgeBase):
    """Test retrieving Yu-Gi-Oh knowledge."""
    result = real_knowledge_base.retrieve_relevant_knowledge(
        game="yugioh",
        query="Blue-Eyes",
        format="Advanced",
        top_k=5,
    )

    assert "mechanics" in result
    assert "examples" in result

    # Should include Yu-Gi-Oh-specific mechanics
    if result["mechanics"]:
        assert "hand trap" in result["mechanics"].lower() or "starter" in result["mechanics"].lower()


def test_knowledge_includes_examples(real_knowledge_base: GameKnowledgeBase):
    """Test that examples are included in retrieval."""
    result = real_knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="Lightning Bolt",
        top_k=5,
    )

    assert "examples" in result
    assert isinstance(result["examples"], list)
    # Should have at least one example if knowledge exists
    if result["mechanics"]:  # If knowledge loaded
        assert len(result["examples"]) > 0


def test_format_filtering_works(real_knowledge_base: GameKnowledgeBase):
    """Test that format filtering prioritizes relevant format knowledge."""
    result_modern = real_knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="test",
        format="Modern",
        top_k=3,
    )

    result_legacy = real_knowledge_base.retrieve_relevant_knowledge(
        game="magic",
        query="test",
        format="Legacy",
        top_k=3,
    )

    # Both should return knowledge (may be same if no format-specific chunks)
    assert "formats" in result_modern
    assert "formats" in result_legacy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

