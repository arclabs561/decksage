#!/usr/bin/env python3
"""Test knowledge retrieval without dependencies."""

import json
from pathlib import Path


def test_retrieval_logic():
    """Test retrieval logic with sample data."""
    # Load a knowledge file directly
    knowledge_file = Path(__file__).parent.parent.parent.parent / "data" / "game_knowledge" / "magic.json"
    
    if not knowledge_file.exists():
        print(f"Knowledge file not found: {knowledge_file}")
        return False
    
    try:
        with open(knowledge_file, encoding="utf-8") as f:
            data = json.load(f)
        
        print("✓ Knowledge file loaded successfully")
        print(f"  Game: {data.get('game', 'N/A')}")
        print(f"  Archetypes: {len(data.get('archetypes', []))}")
        print(f"  Formats: {len(data.get('formats', []))}")
        print(f"  Examples: {len(data.get('examples', []))}")
        
        # Test chunking logic
        mechanics = data.get("mechanics", {})
        if mechanics:
            print(f"  Mechanics: {len(mechanics.get('card_types', []))} card types")
        
        # Test retrieval scoring
        query = "Lightning Bolt"
        query_lower = query.lower()
        
        # Check if query appears in examples
        examples = data.get("examples", [])
        matching_examples = [
            ex for ex in examples
            if query_lower in ex.get("card1", "").lower() or query_lower in ex.get("card2", "").lower()
        ]
        
        print(f"  Matching examples for '{query}': {len(matching_examples)}")
        if matching_examples:
            ex = matching_examples[0]
            print(f"    Example: {ex.get('card1')} vs {ex.get('card2')} (score: {ex.get('score', 'N/A')})")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    print("Testing knowledge retrieval logic...\n")
    success = test_retrieval_logic()
    sys.exit(0 if success else 1)

