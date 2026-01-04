#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy"]
# ///
"""
Test script to verify all graph alignment fixes work correctly.
"""

import sys
from pathlib import Path

from ml.utils.paths import PATHS


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.data.incremental_graph import IncrementalCardGraph
from ml.utils.shared_operations import load_graph_for_jaccard


def test_sqlite_defaults():
    """Test that scripts default to SQLite."""
    print("=" * 70)
    print("TEST 1: SQLite Defaults")
    print("=" * 70)

    test_db = PATHS.graphs / "test_alignment.db"
    if test_db.exists():
        test_db.unlink()

    # Test auto-detection
    graph = IncrementalCardGraph(graph_path=test_db, use_sqlite=True)
    print("✓ SQLite initialization works")

    # Test save/load
    test_deck = {
        "game": "magic",
        "partitions": [{"name": "Main", "cards": [{"name": "Test Card", "count": 1}]}],
    }
    graph.add_deck(test_deck, deck_id="test1")
    graph.save()

    graph2 = IncrementalCardGraph(graph_path=test_db, use_sqlite=True)
    assert len(graph2.nodes) == 1, "Node count mismatch"
    print("✓ SQLite save/load works")

    test_db.unlink()
    print("✓ Test 1 passed\n")


def test_game_filtering():
    """Test game filtering in queries and exports."""
    print("=" * 70)
    print("TEST 2: Game Filtering")
    print("=" * 70)

    test_db = PATHS.graphs / "test_alignment.db"
    if test_db.exists():
        test_db.unlink()

    graph = IncrementalCardGraph(graph_path=test_db, use_sqlite=True)

    # Add MTG deck
    mtg_deck = {
        "game": "magic",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                ],
            }
        ],
    }
    graph.add_deck(mtg_deck, deck_id="mtg1")

    # Add Pokemon deck
    pokemon_deck = {
        "game": "pokemon",
        "partitions": [{"name": "pokemon", "cards": [{"name": "Pikachu", "count": 4}]}],
    }
    graph.add_deck(pokemon_deck, deck_id="pkm1")

    graph.save()

    # Test query_edges with game filter
    mtg_edges = graph.query_edges(game="MTG")
    pokemon_edges = graph.query_edges(game="PKM")
    all_edges = graph.query_edges()

    assert len(mtg_edges) > 0, "Should have MTG edges"
    assert len(pokemon_edges) > 0, "Should have Pokemon edges"
    assert len(all_edges) >= len(mtg_edges) + len(pokemon_edges), (
        "All edges should include filtered"
    )
    print(f"✓ Game filtering works: {len(mtg_edges)} MTG, {len(pokemon_edges)} PKM edges")

    # Test export_edgelist with game filter
    edgelist = PATHS.graphs / "test_edgelist.edg"
    graph.export_edgelist(edgelist, min_weight=1, game="MTG")
    assert edgelist.exists(), "Edgelist should be created"

    # Verify edgelist only has MTG cards
    with open(edgelist) as f:
        lines = f.readlines()
    for line in lines:
        if line.strip() and not line.startswith("#"):
            parts = line.strip().split()
    if len(parts) >= 2:
        card1, card2 = parts[0], parts[1]
    # Both cards should be MTG (Lightning Bolt or Lava Spike)
    assert card1 in ["Lightning", "Lava"] or card2 in ["Lightning", "Lava"], (
        f"Non-MTG card in filtered edgelist: {line}"
    )

    print("✓ Edgelist export with game filter works")

    edgelist.unlink()
    test_db.unlink()
    print("✓ Test 2 passed\n")


def test_shared_operations():
    """Test shared graph loading operations."""
    print("=" * 70)
    print("TEST 3: Shared Operations")
    print("=" * 70)

    test_db = PATHS.graphs / "test_alignment.db"
    if test_db.exists():
        test_db.unlink()

    # Create test graph
    graph = IncrementalCardGraph(graph_path=test_db, use_sqlite=True)
    test_deck = {
        "game": "magic",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                ],
            }
        ],
    }
    graph.add_deck(test_deck, deck_id="test1")
    graph.save()

    # Test load_graph_for_jaccard with graph DB
    adj = load_graph_for_jaccard(graph_db=test_db, game="MTG")
    assert len(adj) > 0, "Should load adjacency from graph"
    assert "Lightning Bolt" in adj or "Lava Spike" in adj, "Should contain test cards"
    print(f"✓ load_graph_for_jaccard works with graph DB: {len(adj)} cards")

    test_db.unlink()
    print("✓ Test 3 passed\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("GRAPH ALIGNMENT TEST SUITE")
    print("=" * 70 + "\n")

    try:
        test_sqlite_defaults()
        test_game_filtering()
        test_shared_operations()

        print("=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"\nError: Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
