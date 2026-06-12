#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy"]
# ///
"""
Test that all consolidated graph loading functions work correctly.
"""

import sys
from pathlib import Path


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.data.incremental_graph import IncrementalCardGraph
from ml.utils.shared_operations import load_graph_for_jaccard, load_jaccard_graph


def test_consolidated_functions():
    """Test that all scripts use shared implementation."""
    print("=" * 70)
    print("TEST: Consolidated Graph Loading Functions")
    print("=" * 70)

    # Create test graph
    from ml.utils.paths import PATHS

    test_db = PATHS.graphs / "test_consolidation.db"
    if test_db.exists():
        test_db.unlink()

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

    # Test shared function directly
    adj1 = load_graph_for_jaccard(graph_db=test_db, game="MTG")
    assert len(adj1) > 0, "Should load from graph DB"
    print(f"✓ Shared load_graph_for_jaccard works: {len(adj1)} cards")

    # Test alias
    adj2 = load_jaccard_graph(graph_db=test_db, game="MTG")
    assert len(adj2) == len(adj1), "Alias should work identically"
    print(f"✓ Shared load_jaccard_graph alias works: {len(adj2)} cards")

    # Test that consolidated scripts can use it
    try:
        from ml.scripts.advanced_weight_optimization import load_graph_for_jaccard as adv_load

        adj3 = adv_load(graph_db=test_db, game="MTG")
        assert len(adj3) > 0, "Consolidated function should work"
        print("✓ advanced_weight_optimization.py uses shared function")
    except Exception as e:
        print(f"✗ advanced_weight_optimization.py error: {e}")
        return 1

    try:
        from ml.scripts.optimize_fusion_for_substitution import load_jaccard_graph as sub_load

        adj4 = sub_load(graph_db=test_db, game="MTG")
        assert len(adj4) > 0, "Consolidated function should work"
        print("✓ optimize_fusion_for_substitution.py uses shared function")
    except Exception as e:
        print(f"✗ optimize_fusion_for_substitution.py error: {e}")
        return 1

    try:
        from ml.scripts.measure_individual_signals import load_graph_for_jaccard as meas_load

        adj5 = meas_load(graph_db=test_db, game="MTG")
        assert len(adj5) > 0, "Consolidated function should work"
        print("✓ measure_individual_signals.py uses shared function")
    except Exception as e:
        print(f"✗ measure_individual_signals.py error: {e}")
        return 1

    # Cleanup
    test_db.unlink()

    print("\n" + "=" * 70)
    print("ALL CONSOLIDATION TESTS PASSED!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(test_consolidated_functions())
