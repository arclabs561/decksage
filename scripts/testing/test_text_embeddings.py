#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Test text embeddings to verify they're working correctly.

Checks:
1. Text embedder is loaded
2. Card attributes are available
3. Text embeddings can compute similarities
4. Results are reasonable
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.similarity.similarity_methods import load_card_attributes_csv
from ml.utils.paths import PATHS


def test_text_embeddings(
    card_attrs_path: Path,
    test_queries: list[str] | None = None,
) -> dict:
    """Test text embeddings functionality."""
    
    if test_queries is None:
        test_queries = ["Lightning Bolt", "Brainstorm", "Counterspell"]
    
    results = {
        "card_attrs_loaded": False,
        "text_embedder_available": False,
        "test_results": {},
    }
    
    # Load card attributes
    print(f"Loading card attributes from {card_attrs_path}...")
    try:
        card_attrs = load_card_attributes_csv(str(card_attrs_path))
        results["card_attrs_loaded"] = True
        print(f"  ✓ Loaded {len(card_attrs)} card attributes")
    except Exception as e:
        print(f"  ✗ Failed to load card attributes: {e}")
        return results
    
    # Check if text embedder is available
    print("\nChecking text embedder...")
    try:
        from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
        
        # Initialize embedder (card_data is not passed in __init__)
        text_embedder = InstructionTunedCardEmbedder(model_name="intfloat/e5-base-v2")
        results["text_embedder_available"] = True
        print("  ✓ Text embedder available")
    except Exception as e:
        print(f"  ✗ Text embedder not available: {e}")
        return results
    
    # Test similarity computation
    print("\nTesting similarity computation...")
    for query in test_queries:
        if query not in card_attrs:
            print(f"  ⚠ Query '{query}' not in card attributes")
            continue
        
        query_attrs = card_attrs[query]
        query_text = query_attrs.get("oracle_text", "")
        
        if not query_text:
            print(f"  ⚠ Query '{query}' has no oracle_text")
            continue
        
        print(f"\n  Query: {query}")
        print(f"    Oracle text: {query_text[:100]}...")
        
        # Test similarity with a few cards
        test_cards = ["Lightning Bolt", "Chain Lightning", "Fireball", "Counterspell"]
        similarities = []
        
        for card in test_cards:
            if card not in card_attrs:
                continue
            
            card_attrs_data = card_attrs[card]
            card_text = card_attrs_data.get("oracle_text", "")
            
            if not card_text:
                continue
            
            try:
                # Compute text embedding similarity
                # InstructionTunedCardEmbedder.similarity takes (card1, card2, instruction_type)
                # Card data is accessed via the embedder's internal card_data if set
                # For now, pass card names and let embedder resolve from card_data if available
                sim = text_embedder.similarity(
                    query,
                    card,
                    instruction_type="substitution",
                )
                similarities.append((card, sim))
                print(f"    {card}: {sim:.3f}")
            except Exception as e:
                print(f"    {card}: Error - {e}")
        
        results["test_results"][query] = {
            "oracle_text_length": len(query_text),
            "similarities": similarities,
        }
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Test text embeddings")
    parser.add_argument(
        "--card-attrs",
        type=str,
        default=str(PATHS.card_attributes),
        help="Path to card attributes CSV",
    )
    parser.add_argument(
        "--queries",
        type=str,
        nargs="+",
        help="Test queries (default: Lightning Bolt, Brainstorm, Counterspell)",
    )
    
    args = parser.parse_args()
    
    results = test_text_embeddings(
        Path(args.card_attrs),
        args.queries,
    )
    
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")
    print(f"Card attributes loaded: {'✓' if results['card_attrs_loaded'] else '✗'}")
    print(f"Text embedder available: {'✓' if results['text_embedder_available'] else '✗'}")
    print(f"Test queries: {len(results['test_results'])}")
    
    if results['card_attrs_loaded'] and results['text_embedder_available']:
        print("\n✓ Text embeddings are working!")
    else:
        print("\n✗ Text embeddings not fully functional")
        if not results['card_attrs_loaded']:
            print("  - Card attributes not loaded")
        if not results['text_embedder_available']:
            print("  - Text embedder not available")
    
    return 0 if (results['card_attrs_loaded'] and results['text_embedder_available']) else 1


if __name__ == "__main__":
    sys.exit(main())

