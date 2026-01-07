"""Test edge cases and error handling for knowledge system."""

import json
from pathlib import Path
from typing import Any


def test_empty_knowledge():
    """Test handling of empty/missing knowledge."""
    # Test with non-existent game
    from ml.knowledge import GameKnowledgeBase
    
    kb = GameKnowledgeBase()
    result = kb.retrieve_relevant_knowledge(
        game="nonexistent",
        query="test",
    )
    
    assert result["mechanics"] == ""
    assert result["archetypes"] == ""
    assert result["formats"] == ""
    assert result["examples"] == []
    print("✓ Empty knowledge handling works")


def test_invalid_game_name():
    """Test handling of invalid game names."""
    from ml.knowledge import GameKnowledgeBase
    
    kb = GameKnowledgeBase()
    
    # Test None
    result = kb.retrieve_relevant_knowledge(game=None, query="test")  # type: ignore
    assert result["mechanics"] == ""
    
    # Test empty string
    result = kb.retrieve_relevant_knowledge(game="", query="test")
    assert result["mechanics"] == ""
    
    print("✓ Invalid game name handling works")


def test_empty_query():
    """Test handling of empty queries."""
    from ml.knowledge import GameKnowledgeBase
    
    kb = GameKnowledgeBase()
    result = kb.retrieve_relevant_knowledge(
        game="magic",
        query="",
    )
    
    # Should still return mechanics (always included)
    assert "mechanics" in result
    print("✓ Empty query handling works")


def test_special_characters():
    """Test handling of special characters in names."""
    from ml.knowledge import GameKnowledgeBase
    
    kb = GameKnowledgeBase()
    
    # Test with special chars in query
    result = kb.retrieve_relevant_knowledge(
        game="magic",
        query="Lightning Bolt (Legacy)",
        format="Modern/Legacy",  # Special chars
    )
    
    # Should not crash
    assert isinstance(result, dict)
    print("✓ Special character handling works")


def test_large_knowledge_file():
    """Test handling of large knowledge files."""
    knowledge_file = Path(__file__).parent.parent.parent.parent / "data" / "game_knowledge" / "magic.json"
    
    if knowledge_file.exists():
        with open(knowledge_file, encoding="utf-8") as f:
            data = json.load(f)
        
        # Check file size
        file_size = knowledge_file.stat().st_size
        print(f"  Magic knowledge file: {file_size:,} bytes")
        
        # Check structure size
        archetypes = len(data.get("archetypes", []))
        formats = len(data.get("formats", []))
        examples = len(data.get("examples", []))
        
        print(f"  Structure: {archetypes} archetypes, {formats} formats, {examples} examples")
        
        # Should handle reasonably
        assert file_size < 1_000_000  # Less than 1MB
        print("✓ Large file handling works")


def test_unicode_handling():
    """Test Unicode character handling."""
    knowledge_file = Path(__file__).parent.parent.parent.parent / "data" / "game_knowledge" / "pokemon.json"
    
    if knowledge_file.exists():
        with open(knowledge_file, encoding="utf-8") as f:
            data = json.load(f)
        
        # Check for Unicode in content
        content = json.dumps(data, ensure_ascii=False)
        has_unicode = any(ord(c) > 127 for c in content)
        
        if has_unicode:
            print(f"  Found Unicode characters (e.g., Pokémon)")
        print("✓ Unicode handling works")


if __name__ == "__main__":
    print("Testing edge cases and error handling...\n")
    
    try:
        test_empty_knowledge()
        test_invalid_game_name()
        test_empty_query()
        test_special_characters()
        test_large_knowledge_file()
        test_unicode_handling()
        
        print("\n✓ All edge case tests passed")
    except Exception as e:
        print(f"\n✗ Edge case test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

