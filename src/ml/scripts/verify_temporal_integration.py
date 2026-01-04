#!/usr/bin/env python3
"""
DEPRECATED: Verify temporal integration in real pipeline scenarios.

This script has been converted to proper pytest tests:
- src/ml/tests/test_temporal_integration.py
- src/ml/tests/test_temporal_edge_cases.py

Run tests with: pytest src/ml/tests/test_temporal_*.py

This script is kept for reference but should not be used for testing.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.data.incremental_graph import IncrementalCardGraph
from ml.utils.paths import PATHS

print("=" * 70)
print("TEMPORAL INTEGRATION VERIFICATION")
print("=" * 70)

issues = []
passed = []


def check(name: str, condition: bool, issue: str | None = None):
    """Check a condition and record result."""
    if condition:
        passed.append(name)
        print(f"✓ {name}")
    else:
        issues.append((name, issue or "Check failed"))
        print(f"✗ {name}: {issue or 'Check failed'}")


print("\n1. Testing deck metadata → format → temporal tracking...")

try:
    test_graph_path = PATHS.graphs / "test_integration_verify.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Simulate real deck with metadata
    deck = {
        "type": {
            "inner": {
                "format": "Modern",
                "eventDate": "2024-06-15",
                "tournamentType": "GP",
                "tournamentSize": 500,
            },
        },
        "game": "magic",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                ],
            },
        ],
    }
    
    deck_id = "test_deck_001"
    timestamp = datetime(2024, 6, 15)
    
    # Set metadata (as update_graph_incremental.py does)
    graph.set_deck_metadata(deck_id, {
        "format": "Modern",
        "event_date": "2024-06-15",
        "tournament_type": "GP",
        "tournament_size": 500,
    })
    
    # Add deck (should extract format from metadata and call update_temporal)
    graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
    
    # Verify edge has temporal data
    edge_key = tuple(sorted(["Lightning Bolt", "Lava Spike"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Edge created with temporal tracking", True)
        check("Format extracted from metadata", "Modern" in str(edge.format_periods) or len(edge.format_periods) > 0)
        check("Monthly count added", "2024-06" in edge.monthly_counts)
        check("Format period created", len(edge.format_periods) > 0)
        
        # Check format period structure
        for period_key, period_data in edge.format_periods.items():
            check(f"Format period '{period_key}' has monthly data", len(period_data) > 0)
            check(f"Format period '{period_key}' includes June", "2024-06" in period_data)
    else:
        check("Edge created", False, "Edge not found")
    
    graph.save()
    
    # Test reload
    graph2 = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    if edge_key in graph2.edges:
        edge2 = graph2.edges[edge_key]
        check("Reload preserves monthly_counts", "2024-06" in edge2.monthly_counts)
        check("Reload preserves format_periods", len(edge2.format_periods) > 0)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Deck metadata integration", False, str(e))


print("\n2. Testing multiple formats on same edge...")

try:
    test_graph_path = PATHS.graphs / "test_multi_format.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Add same cards in different formats
    base_date = datetime(2024, 1, 1)
    for i, format_name in enumerate(["Modern", "Standard", "Legacy"]):
        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [
                        {"name": "Lightning Bolt", "count": 4},
                        {"name": "Shock", "count": 4},
                    ],
                },
            ],
        }
        deck_id = f"deck_{format_name}_{i}"
        timestamp = base_date + timedelta(days=i * 60)
        
        graph.set_deck_metadata(deck_id, {"format": format_name})
        graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
    
    edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Multiple formats tracked", len(edge.format_periods) >= 3)
        check("All formats have data", all(len(period) > 0 for period in edge.format_periods.values()))
        
        # Check each format period
        format_names = set()
        for period_key in edge.format_periods.keys():
            if "Modern" in period_key:
                format_names.add("Modern")
            if "Standard" in period_key:
                format_names.add("Standard")
            if "Legacy" in period_key:
                format_names.add("Legacy")
        check("All three formats present", len(format_names) == 3)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Multiple formats", False, str(e))


print("\n3. Testing temporal accumulation across time...")

try:
    test_graph_path = PATHS.graphs / "test_temporal_accumulation.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Add same deck multiple times across months
    base_date = datetime(2024, 1, 15)
    for i in range(6):
        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [
                        {"name": "Test Card A", "count": 4},
                        {"name": "Test Card B", "count": 4},
                    ],
                },
            ],
        }
        deck_id = f"accum_deck_{i}"
        timestamp = base_date + timedelta(days=i * 30)  # Monthly
        
        graph.set_deck_metadata(deck_id, {"format": "Modern"})
        graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
    
    edge_key = tuple(sorted(["Test Card A", "Test Card B"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Temporal accumulation works", len(edge.monthly_counts) >= 3)
        check("Multiple months tracked", sum(edge.monthly_counts.values()) >= 6)
        
        # Check that counts increase
        total_count = sum(edge.monthly_counts.values())
        check("Counts accumulate correctly", total_count >= 6)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Temporal accumulation", False, str(e))


print("\n4. Testing edge case: deck without format...")

try:
    test_graph_path = PATHS.graphs / "test_no_format.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Add deck without format metadata
    deck = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Card X", "count": 4},
                    {"name": "Card Y", "count": 4},
                ],
            },
        ],
    }
    
    graph.add_deck(deck, timestamp=datetime(2024, 1, 15), deck_id="no_format_deck")
    
    edge_key = tuple(sorted(["Card X", "Card Y"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Works without format", len(edge.monthly_counts) > 0)
        check("Monthly counts still tracked", "2024-01" in edge.monthly_counts)
        # Format periods may be empty, which is OK
        check("Handles missing format gracefully", True)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("No format handling", False, str(e))


print("\n5. Testing edge case: deck with round results...")

try:
    test_graph_path = PATHS.graphs / "test_round_results.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    deck = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Card P", "count": 4},
                    {"name": "Card Q", "count": 4},
                ],
            },
        ],
        "roundResults": [
            {"roundNumber": 1, "opponentDeck": "Jund", "result": "W"},
            {"roundNumber": 2, "opponentDeck": "Burn", "result": "L"},
        ],
    }
    
    deck_id = "round_results_deck"
    graph.set_deck_metadata(deck_id, {
        "format": "Modern",
        "round_results": deck["roundResults"],
    })
    graph.add_deck(deck, timestamp=datetime(2024, 1, 15), deck_id=deck_id)
    
    # Check that deck metadata was stored
    metadata = graph._deck_metadata_cache.get(deck_id, {})
    check("Round results stored in metadata", "round_results" in metadata)
    if "round_results" in metadata:
        check("Round results preserved", len(metadata["round_results"]) == 2)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Round results handling", False, str(e))


print("\n6. Testing real-world deck structure (nested type.inner)...")

try:
    test_graph_path = PATHS.graphs / "test_nested_structure.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Real deck structure from scrapers
    deck = {
        "type": {
            "inner": {
                "format": "Standard",
                "eventDate": "2024-08-01",
                "tournamentType": "Regional",
                "tournamentSize": 200,
                "location": "Las Vegas, NV",
            },
        },
        "game": "magic",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Strike", "count": 4},
                    {"name": "Shock", "count": 4},
                ],
            },
        ],
    }
    
    deck_id = "nested_deck_001"
    timestamp = datetime(2024, 8, 1)
    
    # Extract format (as update_graph_incremental.py does)
    format_value = (
        deck.get("format")
        or (deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}).get("format")
    )
    
    graph.set_deck_metadata(deck_id, {
        "format": format_value,
        "event_date": deck["type"]["inner"]["eventDate"],
    })
    graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
    
    edge_key = tuple(sorted(["Lightning Strike", "Shock"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Nested structure handled", "2024-08" in edge.monthly_counts)
        check("Format extracted from nested", len(edge.format_periods) > 0)
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Nested structure", False, str(e))


# Summary
print("\n" + "=" * 70)
print(f"RESULTS: {len(passed)} passed, {len(issues)} issues")
print("=" * 70)

if issues:
    print("\nISSUES:")
    for name, issue in issues:
        print(f"  ✗ {name}: {issue}")
    sys.exit(1)
else:
    print("\n✓ All integration checks passed!")
    sys.exit(0)

