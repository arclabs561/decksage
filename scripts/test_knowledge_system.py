#!/usr/bin/env python3
"""Quick test script for knowledge injection system."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ml.knowledge import GameKnowledgeBase, retrieve_game_knowledge


def main():
    """Test knowledge retrieval."""
    print("Testing Game Knowledge Injection System\n")
    
    kb = GameKnowledgeBase()
    
    # Test Magic
    print("=" * 60)
    print("Magic: The Gathering")
    print("=" * 60)
    result = kb.retrieve_relevant_knowledge(
        game="magic",
        query="Lightning Bolt",
        format="Modern",
        archetype="Burn",
        top_k=3,
    )
    print(f"Mechanics: {len(result['mechanics'])} chars")
    print(f"Archetypes: {len(result['archetypes'])} chars")
    print(f"Formats: {len(result['formats'])} chars")
    print(f"Examples: {len(result['examples'])} examples")
    if result['examples']:
        print(f"  Example: {result['examples'][0].get('card1', 'N/A')} vs {result['examples'][0].get('card2', 'N/A')}")
    
    # Test Pokemon
    print("\n" + "=" * 60)
    print("Pokémon TCG")
    print("=" * 60)
    result = kb.retrieve_relevant_knowledge(
        game="pokemon",
        query="Pikachu",
        format="Standard",
        top_k=3,
    )
    print(f"Mechanics: {len(result['mechanics'])} chars")
    print(f"Archetypes: {len(result['archetypes'])} chars")
    print(f"Formats: {len(result['formats'])} chars")
    print(f"Examples: {len(result['examples'])} examples")
    
    # Test Yu-Gi-Oh
    print("\n" + "=" * 60)
    print("Yu-Gi-Oh!")
    print("=" * 60)
    result = kb.retrieve_relevant_knowledge(
        game="yugioh",
        query="Blue-Eyes",
        format="Advanced",
        top_k=3,
    )
    print(f"Mechanics: {len(result['mechanics'])} chars")
    print(f"Archetypes: {len(result['archetypes'])} chars")
    print(f"Formats: {len(result['formats'])} chars")
    print(f"Examples: {len(result['examples'])} examples")
    
    print("\n" + "=" * 60)
    print("✓ Knowledge system working!")
    print("=" * 60)


if __name__ == "__main__":
    main()

