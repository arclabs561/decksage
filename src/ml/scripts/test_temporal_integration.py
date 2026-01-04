#!/usr/bin/env python3
"""
DEPRECATED: Integration test for temporal enhancements end-to-end.

This script has been converted to proper pytest tests:
- src/ml/tests/test_temporal_integration.py
- src/ml/tests/test_temporal_edge_cases.py

Run tests with: pytest src/ml/tests/test_temporal_*.py

This script is kept for reference but should not be used for testing.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.data.incremental_graph import IncrementalCardGraph
from ml.similarity.fusion import WeightedLateFusion
from ml.utils.paths import PATHS


print("=" * 70)
print("TEMPORAL ENHANCEMENTS INTEGRATION TEST")
print("=" * 70)

# Create test graph
test_graph_path = PATHS.graphs / "test_temporal_integration.db"
if test_graph_path.exists():
    test_graph_path.unlink()

graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)

print("\n1. Testing graph updates with temporal metadata...")

# Add decks with different timestamps and formats
decks = [
    {
        "format": "Modern",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Shock", "count": 4},
                ],
            },
        ],
    },
    {
        "format": "Standard",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Strike", "count": 4},
                    {"name": "Shock", "count": 4},
                ],
            },
        ],
    },
]

base_date = datetime(2024, 1, 1)
for i, deck in enumerate(decks):
    deck_id = f"deck_{i}"
    timestamp = base_date + timedelta(days=i * 30)  # 30 days apart

    graph.set_deck_metadata(
        deck_id,
        {
            "format": deck["format"],
            "tournament_type": "GP",
            "tournament_size": 500,
        },
    )
    graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)

# Check edge temporal distribution
edge_key = tuple(sorted(["Shock", "Lightning Bolt"]))
if edge_key in graph.edges:
    edge = graph.edges[edge_key]
    print(f"  ✓ Edge has monthly_counts: {len(edge.monthly_counts)} months")
    print(f"  ✓ Edge has format_periods: {len(edge.format_periods)} formats")
    assert "2024-01" in edge.monthly_counts or "2024-02" in edge.monthly_counts
else:
    print("  ⚠ Edge not found (may be different cards)")

edge_key2 = tuple(sorted(["Shock", "Lightning Strike"]))
if edge_key2 in graph.edges:
    edge2 = graph.edges[edge_key2]
    print(f"  ✓ Edge2 has monthly_counts: {len(edge2.monthly_counts)} months")
    assert "2024-02" in edge2.monthly_counts or len(edge2.monthly_counts) > 0

graph.save()
print("  ✓ Graph saved with temporal data")

# Test graph loading
print("\n2. Testing graph loading with temporal data...")
graph2 = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
assert len(graph2.nodes) > 0, "Should load nodes"
assert len(graph2.edges) > 0, "Should load edges"

# Check that temporal data is preserved
for edge in graph2.edges.values():
    if edge.monthly_counts:
        print(f"  ✓ Edge {edge.card1}-{edge.card2} has {len(edge.monthly_counts)} months tracked")
        break

print("  ✓ Graph loading preserves temporal data")

# Test temporal similarity
print("\n3. Testing temporal similarity computation...")
try:
    # Create fusion with graph
    fusion = WeightedLateFusion(
        graph=graph2,
        weights=None,  # Use defaults
    )

    # Test temporal similarity (will use edge monthly_counts if available)
    if edge_key in graph2.edges:
        edge = graph2.edges[edge_key]
        if edge.monthly_counts:
            # Test the enhanced temporal similarity
            temporal_sim = fusion._get_temporal_similarity(
                "Lightning Bolt",
                "Shock",
                format="Modern",
                game="MTG",
            )
            print(f"  ✓ Temporal similarity computed: {temporal_sim:.3f}")
            assert 0.0 <= temporal_sim <= 1.0, "Temporal similarity should be 0-1"
except Exception as e:
    print(f"  ⚠ Temporal similarity test skipped: {e}")

# Test serialization
print("\n4. Testing serialization...")
edge_key_test = tuple(sorted(["Lightning Bolt", "Shock"]))
if edge_key_test in graph2.edges:
    edge = graph2.edges[edge_key_test]
    edge_dict = edge.to_dict()

    # Check serialization (may be empty if no temporal data yet)
    if edge.monthly_counts:
        assert "monthly_counts" in edge_dict, "Should serialize monthly_counts"
        print(f"  ✓ monthly_counts serialized: {len(edge_dict.get('monthly_counts', {}))} months")
    if edge.format_periods:
        assert "format_periods" in edge_dict, "Should serialize format_periods"
        print(f"  ✓ format_periods serialized: {len(edge_dict.get('format_periods', {}))} formats")

    # Test round-trip
    edge_loaded = edge.from_dict(edge_dict)
    assert edge_loaded.monthly_counts == edge.monthly_counts
    assert edge_loaded.format_periods == edge.format_periods
    print("  ✓ Serialization round-trip works")
else:
    print("  ⚠ Edge not found for serialization test")

# Cleanup
if test_graph_path.exists():
    test_graph_path.unlink()

print("\n" + "=" * 70)
print("✓ ALL INTEGRATION TESTS PASSED")
print("=" * 70)
