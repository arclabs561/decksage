#!/usr/bin/env python3
"""
Example script demonstrating visual embeddings usage.

Shows how to:
1. Initialize visual embedder
2. Embed cards from image URLs
3. Compute visual similarity
4. Use in fusion system
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.similarity.visual_embeddings import get_visual_embedder
from ml.similarity.fusion import FusionWeights, WeightedLateFusion


def example_basic_usage():
    """Basic visual embedding usage."""
    print("=" * 60)
    print("Example 1: Basic Visual Embedding")
    print("=" * 60)

    # Get visual embedder
    embedder = get_visual_embedder()

    # Example cards with image URLs
    # Note: These are example URLs - replace with actual card image URLs
    card1 = {
        "name": "Lightning Bolt",
        "image_url": "https://cards.scryfall.io/normal/front/0/6/06a3b5e7-8b78-4c4e-9c5a-8e3f2d1c0b9a.jpg",
    }
    card2 = {
        "name": "Shock",
        "image_url": "https://cards.scryfall.io/normal/front/1/7/17a4c6f8-9c89-5d5f-0d6b-9f4g3e2d1c0b.jpg",
    }

    print(f"\nEmbedding {card1['name']}...")
    try:
        emb1 = embedder.embed_card(card1)
        print(f"  ✓ Embedding shape: {emb1.shape}")
        print(f"  ✓ Embedding dimension: {emb1.shape[0]}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        print("  (This is expected if image URL is not accessible)")

    print(f"\nComputing similarity between {card1['name']} and {card2['name']}...")
    try:
        similarity = embedder.similarity(card1, card2)
        print(f"  ✓ Visual similarity: {similarity:.3f}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        print("  (This is expected if image URLs are not accessible)")


def example_fusion_integration():
    """Visual embeddings in fusion system."""
    print("\n" + "=" * 60)
    print("Example 2: Fusion Integration")
    print("=" * 60)

    # Create fusion weights with visual embeddings
    weights = FusionWeights(
        embed=0.20,  # Co-occurrence
        jaccard=0.15,  # Jaccard
        functional=0.10,  # Functional tags
        text_embed=0.25,  # Text embeddings
        visual_embed=0.20,  # Visual embeddings
        gnn=0.30,  # GNN
    )

    print(f"\nFusion weights (normalized):")
    normalized = weights.normalized()
    print(f"  Co-occurrence: {normalized.embed:.2%}")
    print(f"  Jaccard: {normalized.jaccard:.2%}")
    print(f"  Functional: {normalized.functional:.2%}")
    print(f"  Text embeddings: {normalized.text_embed:.2%}")
    print(f"  Visual embeddings: {normalized.visual_embed:.2%}")
    print(f"  GNN: {normalized.gnn:.2%}")

    print("\n✓ Visual embeddings integrated into fusion system")
    print("  (Fusion will use visual embeddings when visual_embedder is provided)")


def example_batch_processing():
    """Batch processing example."""
    print("\n" + "=" * 60)
    print("Example 3: Batch Processing")
    print("=" * 60)

    embedder = get_visual_embedder()

    # Example: Batch of cards
    cards = [
        {"name": "Card1", "image_url": "https://example.com/card1.png"},
        {"name": "Card2", "image_url": "https://example.com/card2.png"},
        {"name": "Card3", "image_url": "https://example.com/card3.png"},
    ]

    print(f"\nBatch embedding {len(cards)} cards...")
    try:
        embeddings = embedder.embed_batch(cards)
        print(f"  ✓ Embeddings shape: {embeddings.shape}")
        print(f"  ✓ Processed {embeddings.shape[0]} cards")
        print(f"  ✓ Embedding dimension: {embeddings.shape[1]}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        print("  (This is expected if image URLs are not accessible)")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Visual Embeddings Examples")
    print("=" * 60)
    print("\nThis script demonstrates visual embeddings usage.")
    print("Note: Examples may fail if image URLs are not accessible.")
    print("This is expected - the code structure is what matters.\n")

    try:
        example_basic_usage()
        example_fusion_integration()
        example_batch_processing()

        print("\n" + "=" * 60)
        print("Examples Complete")
        print("=" * 60)
        print("\nFor real usage:")
        print("1. Ensure cards have valid image URLs")
        print("2. Set VISUAL_EMBEDDER_MODEL environment variable (optional)")
        print("3. Visual embeddings will be used automatically in fusion")
        print("\nSee docs/VISUAL_EMBEDDINGS_USAGE.md for more details.")
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

