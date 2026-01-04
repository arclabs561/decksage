#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Test hybrid embedding system end-to-end.

Tests:
1. Graph incremental updates
2. Instruction-tuned embeddings (zero-shot)
3. GNN embeddings (inductive)
4. Fusion system integration
"""

from __future__ import annotations

import argparse
import sys

from ..data.incremental_graph import IncrementalCardGraph
from ..scripts.integrate_hybrid_embeddings import (
    create_fusion_with_hybrid_embeddings,
    load_hybrid_embeddings,
)
from ..utils.paths import PATHS


def test_graph_updates() -> bool:
    """Test incremental graph updates."""
    logger.info("Testing incremental graph updates...")

    try:
        graph = IncrementalCardGraph()

        # Test deck
        test_deck = {
            "deck_id": "test_001",
            "cards": [
                {"name": "Lightning Bolt", "count": 4},
                {"name": "Shock", "count": 4},
                {"name": "Mountain", "count": 20},
            ],
        }

        graph.add_deck(test_deck)

        # Check neighbors
        neighbors = graph.get_neighbors("Lightning Bolt")
        assert "Shock" in neighbors, "Shock should be neighbor of Lightning Bolt"

        stats = graph.get_statistics()
        assert stats["num_nodes"] >= 3, "Should have at least 3 nodes"
        assert stats["num_edges"] >= 1, "Should have at least 1 edge"

        logger.info("✓ Graph updates working")
        return True

    except Exception as e:
        logger.error(f"✗ Graph updates failed: {e}")
        return False


def test_instruction_tuned() -> bool:
    """Test instruction-tuned embeddings."""
    logger.info("Testing instruction-tuned embeddings...")

    try:
        from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

        embedder = InstructionTunedCardEmbedder()

        # Test new card (zero-shot)
        new_card = {
            "name": "Lightning Strike 2.0",
            "type_line": "Instant",
            "oracle_text": "Lightning Strike 2.0 deals 3 damage to any target.",
        }

        embedding = embedder.embed_card(new_card, instruction_type="substitution")
        assert embedding is not None, "Should generate embedding"
        assert len(embedding) > 0, "Embedding should have dimensions"

        # Test similarity
        similarity = embedder.similarity(
            "Lightning Bolt",
            "Shock",
            instruction_type="substitution",
        )
        assert 0.0 <= similarity <= 1.0, "Similarity should be in [0, 1]"

        logger.info("✓ Instruction-tuned embeddings working")
        return True

    except Exception as e:
        logger.error(f"✗ Instruction-tuned embeddings failed: {e}")
        return False


def test_gnn_incremental() -> bool:
    """Test GNN incremental updates."""
    logger.info("Testing GNN incremental updates...")

    try:
        from ..similarity.gnn_embeddings import CardGNNEmbedder

        # Create minimal graph for testing
        graph = IncrementalCardGraph()
        test_deck = {
            "cards": [
                {"name": "Lightning Bolt", "count": 4},
                {"name": "Shock", "count": 4},
            ],
        }
        graph.add_deck(test_deck)

        # Export edgelist
        edgelist_path = PATHS.data / "graphs" / "test_edgelist.edg"
        graph.export_edgelist(edgelist_path, min_weight=1)

        # Train minimal GNN
        embedder = CardGNNEmbedder(model_type="GraphSAGE", hidden_dim=64, num_layers=1)
        embedder.train(edgelist_path, epochs=5, output_path=PATHS.embeddings / "test_gnn.json")

        # Test incremental update
        new_cards = ["Lightning Strike"]
        graph.add_deck(
            {
                "cards": [
                    {"name": "Lightning Strike", "count": 4},
                    {"name": "Lightning Bolt", "count": 4},
                ]
            }
        )

        # Add new card incrementally
        embedder.add_new_cards(new_cards, graph)

        # Check embedding exists
        assert "Lightning Strike" in embedder.embeddings, "New card should have embedding"

        logger.info("✓ GNN incremental updates working")
        return True

    except Exception as e:
        logger.error(f"✗ GNN incremental updates failed: {e}")
        return False


def test_fusion_integration() -> bool:
    """Test fusion system integration."""
    logger.info("Testing fusion system integration...")

    try:
        # Load hybrid embeddings
        embeddings_data = load_hybrid_embeddings(
            gnn_model_path=PATHS.embeddings / "test_gnn.json"
            if (PATHS.embeddings / "test_gnn.json").exists()
            else None,
        )

        # Create fusion
        fusion = create_fusion_with_hybrid_embeddings(embeddings_data)

        # Test query
        results = fusion.find_similar("Lightning Bolt", topn=5)
        assert len(results) > 0, "Should return results"

        logger.info("✓ Fusion integration working")
        return True

    except Exception as e:
        logger.error(f"✗ Fusion integration failed: {e}")
        return False


def main() -> int:
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test hybrid embedding system")
    parser.add_argument(
        "--test",
        choices=["all", "graph", "instruction", "gnn", "fusion"],
        default="all",
        help="Which test to run",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Testing Hybrid Embedding System")
    logger.info("=" * 60)

    results = {}

    if args.test in ["all", "graph"]:
        results["graph"] = test_graph_updates()

    if args.test in ["all", "instruction"]:
        results["instruction"] = test_instruction_tuned()

    if args.test in ["all", "gnn"]:
        results["gnn"] = test_gnn_incremental()

    if args.test in ["all", "fusion"]:
        results["fusion"] = test_fusion_integration()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Results")
    logger.info("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {test_name}: {status}")

    all_passed = all(results.values())
    logger.info("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
