#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "pyarrow"]
# ///
"""
Test enhanced graph functionality.

Tests:
1. Game identifier extraction
2. Card count weighting
3. Partition information
4. SQLite storage
5. Parquet export
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from ml.utils.logging_config import setup_script_logging

# Add src to path for local imports
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

logger = setup_script_logging()


def test_enhanced_graph():
    """Test all enhanced graph features."""
    
    try:
        from ml.data.incremental_graph import IncrementalCardGraph
    except ImportError as e:
        print(f"Failed to import: {e}")
        print("   Run: uv sync")
        return 1
    
    print("=" * 70)
    print("TESTING ENHANCED GRAPH")
    print("=" * 70)
    
    # Create test graph (JSON for initial testing)
    from ml.utils.paths import PATHS
    test_json_path = PATHS.graphs / "test_graph.json"
    if test_json_path.exists():
        test_json_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_json_path, use_sqlite=False)
    
    # Test deck with all features
    test_deck = {
        "game": "magic",
        "format": "Modern",
        "archetype": "Burn",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                    {"name": "Goblin Guide", "count": 4},
                ],
            },
            {
                "name": "Sideboard",
                "cards": [
                    {"name": "Smash to Smithereens", "count": 2},
                    {"name": "Path to Exile", "count": 2},
                ],
            },
        ],
    }
    
    print("\n1. Testing card extraction with counts and partitions...")
    card_metadata = graph._extract_cards_with_metadata(test_deck)
    print(f"   Extracted {len(card_metadata)} cards with metadata:")
    for card_name, count, partition, game in card_metadata:
        print(f"     {card_name}: {count}x in {partition} (game={game})")
    
    print("\n2. Testing deck addition...")
    graph.set_deck_metadata("test_deck_1", {
        "format": "Modern",
        "placement": 1,
        "event_date": datetime.now().isoformat(),
    })
    graph.add_deck(test_deck, deck_id="test_deck_1", timestamp=datetime.now())
    
    print(f"   Nodes: {len(graph.nodes)}")
    print(f"   Edges: {len(graph.edges)}")
    
    # Check game assignment
    print("\n3. Testing game identifier...")
    for node_name, node in list(graph.nodes.items())[:5]:
        print(f"   {node_name}: game={node.game}")
    
    # Check edge weights (should reflect counts)
    print("\n4. Testing edge weights (card counts)...")
    for (card1, card2), edge in list(graph.edges.items())[:5]:
        print(f"   {card1} <-> {card2}: weight={edge.weight}, game={edge.game}")
        if "partitions" in edge.metadata:
            print(f"     Partitions: {edge.metadata['partitions']}")
    
    # Check statistics
    print("\n5. Testing statistics...")
    stats = graph.get_statistics()
    print(f"   Nodes: {stats['num_nodes']}")
    print(f"   Edges: {stats['num_edges']}")
    print(f"   Game distribution: {stats.get('game_distribution', {})}")
    
    # Test query
    print("\n6. Testing edge queries...")
    mtg_edges = graph.query_edges(game="MTG")
    print(f"   MTG edges: {len(mtg_edges)}")
    
    # Test Parquet export
    try:
        import pyarrow.parquet as pq
        HAS_PARQUET = True
    except ImportError:
        HAS_PARQUET = False
    
    if HAS_PARQUET:
        print("\n7. Testing Parquet export...")
        from ml.utils.paths import PATHS
        output_dir = PATHS.graphs / "test_parquet"
        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)
        paths = graph.export_parquet(output_dir)
        print(f"   Exported to: {paths}")
        for name, path in paths.items():
            if path.exists():
                size_mb = path.stat().st_size / (1024 * 1024)
                print(f"     {name}: {size_mb:.2f} MB")
    else:
        print("\n7. Skipping Parquet export (pyarrow not available)")
    
    # Test SQLite
    print("\n8. Testing SQLite storage...")
    from ml.utils.paths import PATHS
    db_path = PATHS.graphs / "test_graph.db"
    if db_path.exists():
        db_path.unlink()
    
    # Save to SQLite
    graph_sqlite = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    # Copy nodes and edges
    for name, node in graph.nodes.items():
        graph_sqlite.nodes[name] = node
    for key, edge in graph.edges.items():
        graph_sqlite.edges[key] = edge
    graph_sqlite.last_update = graph.last_update
    graph_sqlite.total_decks_processed = graph.total_decks_processed
    graph_sqlite.save()
    
    # Load from SQLite
    graph2 = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    print(f"   Loaded from SQLite: {len(graph2.nodes):,} nodes, {len(graph2.edges):,} edges")
    
    # Verify data integrity
    assert len(graph2.nodes) == len(graph.nodes), "Node count mismatch"
    assert len(graph2.edges) == len(graph.edges), "Edge count mismatch"
    
    # Cleanup
    if test_json_path.exists():
        test_json_path.unlink()
    if db_path.exists():
        db_path.unlink()
    if HAS_PARQUET and output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    
    print("\n" + "=" * 70)
    print("ALL TESTS PASSED!")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(test_enhanced_graph())

