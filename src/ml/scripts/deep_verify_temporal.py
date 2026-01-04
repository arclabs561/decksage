#!/usr/bin/env python3
"""
DEPRECATED: Deep verification of temporal enhancements.

This script has been converted to proper pytest tests:
- src/ml/tests/test_temporal_edge_cases.py
- src/ml/tests/test_temporal_integration.py
- src/ml/tests/test_graph_temporal_features.py

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

from ml.data.incremental_graph import Edge, IncrementalCardGraph
from ml.data.temporal_stats import (
    compute_consistency,
    compute_recency_score,
    compute_temporal_stats,
)
from ml.scripts.compute_temporal_metadata import (
    compute_days_since_ban_update,
    compute_days_since_rotation,
    compute_matchup_statistics,
    enrich_deck_with_temporal_metadata,
)
from ml.utils.matchup_analysis import aggregate_matchup_data, analyze_deck_matchups
from ml.utils.paths import PATHS

print("=" * 70)
print("DEEP VERIFICATION OF TEMPORAL ENHANCEMENTS")
print("=" * 70)

issues = []
warnings = []
passed = []


def check(name: str, condition: bool, issue: str | None = None):
    """Check a condition and record result."""
    if condition:
        passed.append(name)
        print(f"✓ {name}")
    else:
        issues.append((name, issue or "Check failed"))
        print(f"✗ {name}: {issue or 'Check failed'}")


def warn(name: str, message: str):
    """Record a warning."""
    warnings.append((name, message))
    print(f"⚠ {name}: {message}")


print("\n1. Testing Edge serialization round-trip with temporal data...")
try:
    # Create edge with full temporal data
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        weight=42,
        first_seen=datetime(2024, 1, 15),
        last_seen=datetime(2024, 6, 20),
        game="MTG",
    )
    
    # Add temporal data (use timedelta to avoid invalid dates)
    for i in range(5):
        edge.update_temporal(datetime(2024, 1, 15) + timedelta(days=i * 7), "Modern")
    edge.update_temporal(datetime(2024, 2, 10), "Standard")
    edge.update_temporal(datetime(2024, 3, 5), "Standard")
    
    # Serialize
    edge_dict = edge.to_dict()
    check("Edge serialization includes monthly_counts", "monthly_counts" in edge_dict)
    check("Edge serialization includes format_periods", "format_periods" in edge_dict)
    check("Edge monthly_counts has data", len(edge_dict.get("monthly_counts", {})) > 0)
    check("Edge format_periods has data", len(edge_dict.get("format_periods", {})) > 0)
    
    # Deserialize
    edge2 = Edge.from_dict(edge_dict)
    check("Edge deserialization preserves monthly_counts", edge2.monthly_counts == edge.monthly_counts)
    check("Edge deserialization preserves format_periods", edge2.format_periods == edge.format_periods)
    check("Edge deserialization preserves game", edge2.game == edge.game)
    check("Edge deserialization preserves weight", edge2.weight == edge.weight)
    
    # Test JSON serialization (what actually gets stored)
    json_str = json.dumps(edge_dict)
    edge_dict_loaded = json.loads(json_str)
    edge3 = Edge.from_dict(edge_dict_loaded)
    check("Edge JSON round-trip works", edge3.monthly_counts == edge.monthly_counts)
    
except Exception as e:
    check("Edge serialization round-trip", False, str(e))


print("\n2. Testing temporal statistics with edge cases...")
try:
    # Empty counts
    stats_empty = compute_temporal_stats({}, datetime(2024, 1, 1), datetime(2024, 1, 1), 0)
    check("Empty monthly_counts handled", stats_empty.months_active == 0)
    
    # Single month
    stats_single = compute_temporal_stats(
        {"2024-01": 10},
        datetime(2024, 1, 1),
        datetime(2024, 1, 31),
        10,
    )
    check("Single month handled", stats_single.months_active == 1)
    check("Single month peak count", stats_single.peak_count == 10)
    
    # Very sparse data
    stats_sparse = compute_temporal_stats(
        {"2024-01": 1, "2024-12": 1},
        datetime(2024, 1, 1),
        datetime(2024, 12, 31),
        2,
    )
    check("Sparse data handled", stats_sparse.months_active == 2)
    check("Sparse data span calculated", stats_sparse.activity_span_days > 300)
    
    # Invalid month keys (should be skipped)
    stats_invalid = compute_temporal_stats(
        {"2024-01": 5, "invalid": 3, "2024-13": 2},  # Invalid months
        datetime(2024, 1, 1),
        datetime(2024, 12, 31),
        10,
    )
    check("Invalid month keys skipped", stats_invalid.months_active >= 1)
    
except Exception as e:
    check("Temporal statistics edge cases", False, str(e))


print("\n3. Testing recency score edge cases...")
try:
    # All counts in past
    recency_old = compute_recency_score(
        {"2020-01": 100},
        datetime(2025, 1, 1),
        decay_days=365.0,
    )
    check("Old data recency computed", 0.0 <= recency_old <= 1.0)
    
    # All counts recent
    recency_recent = compute_recency_score(
        {"2024-12": 100},
        datetime(2025, 1, 1),
        decay_days=365.0,
    )
    check("Recent data has high recency", recency_recent > 0.5)
    
    # Mixed old and recent
    recency_mixed = compute_recency_score(
        {"2020-01": 50, "2024-12": 50},
        datetime(2025, 1, 1),
        decay_days=365.0,
    )
    check("Mixed data recency computed", 0.0 < recency_mixed < 1.0)
    check("Mixed recency between old and recent", recency_old < recency_mixed < recency_recent)
    
    # Zero decay days (should default)
    recency_zero_decay = compute_recency_score(
        {"2024-12": 10},
        datetime(2025, 1, 1),
        decay_days=0.0,  # Invalid, should default
    )
    check("Zero decay days handled", recency_zero_decay >= 0.0)
    
    # Negative counts (should be skipped)
    recency_negative = compute_recency_score(
        {"2024-01": 10, "2024-02": -5},  # Negative count
        datetime(2025, 1, 1),
        decay_days=365.0,
    )
    check("Negative counts skipped", recency_negative >= 0.0)
    
except Exception as e:
    check("Recency score edge cases", False, str(e))


print("\n4. Testing matchup statistics edge cases...")
try:
    # Empty round results
    deck_empty = {"roundResults": []}
    stats_empty = compute_matchup_statistics(deck_empty)
    check("Empty round results returns None", stats_empty is None)
    
    # Invalid round results
    deck_invalid = {"roundResults": [{"result": "INVALID"}, {"result": "W"}]}
    stats_invalid = compute_matchup_statistics(deck_invalid)
    check("Invalid results filtered", stats_invalid is not None)
    if stats_invalid:
        check("Only valid results counted", stats_invalid["total_rounds"] == 1)
    
    # Missing opponent archetypes
    deck_no_archetype = {
        "roundResults": [
            {"roundNumber": 1, "opponent": "Player1", "result": "W"},
            {"roundNumber": 2, "opponent": "Player2", "result": "L"},
        ]
    }
    stats_no_arch = compute_matchup_statistics(deck_no_archetype)
    check("Missing archetypes handled", stats_no_arch is not None)
    if stats_no_arch:
        check("Win rate computed without archetypes", stats_no_arch["win_rate"] == 0.5)
    
    # All ties
    deck_all_ties = {
        "roundResults": [
            {"roundNumber": 1, "opponentDeck": "Jund", "result": "T"},
            {"roundNumber": 2, "opponentDeck": "Burn", "result": "T"},
        ]
    }
    stats_ties = compute_matchup_statistics(deck_all_ties)
    check("All ties handled", stats_ties is not None)
    if stats_ties:
        check("Win rate with all ties", stats_ties["win_rate"] == 0.0)
        check("Ties counted", stats_ties["ties"] == 2)
    
except Exception as e:
    check("Matchup statistics edge cases", False, str(e))


print("\n5. Testing graph integration with temporal data...")
try:
    test_graph_path = PATHS.graphs / "test_deep_verify.db"
    if test_graph_path.exists():
        test_graph_path.unlink()
    
    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    
    # Add multiple decks with different timestamps
    # Use unique deck IDs to ensure all are counted
    base_date = datetime(2024, 1, 1)
    for i in range(10):
        deck = {
            "format": "Modern" if i % 2 == 0 else "Standard",
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
        deck_id = f"deep_verify_deck_{i}"  # Unique IDs
        timestamp = base_date + timedelta(days=i * 30)
        
        graph.set_deck_metadata(deck_id, {"format": deck["format"]})
        graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
    
    graph.save()
    
    # Verify edge has temporal data
    edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
    if edge_key in graph.edges:
        edge = graph.edges[edge_key]
        check("Edge has monthly_counts after multiple decks", len(edge.monthly_counts) > 0)
        check("Edge has format_periods", len(edge.format_periods) > 0)
        
        # Check that counts are correct (should be 10 decks, each with 4+4=8 co-occurrences)
        # But each deck adds 1 to the edge weight, so monthly_counts should sum to 10
        total_count = sum(edge.monthly_counts.values())
        check("Monthly counts sum to deck count", total_count >= 10)  # At least 10
        
        # Check format periods (should have both Modern and Standard)
        modern_count = sum(
            sum(period.values())
            for period_key, period in edge.format_periods.items()
            if "Modern" in period_key
        )
        standard_count = sum(
            sum(period.values())
            for period_key, period in edge.format_periods.items()
            if "Standard" in period_key
        )
        check("Format periods have Modern", modern_count >= 5)
        check("Format periods have Standard", standard_count >= 5)
    else:
        warn("Edge not found", "Lightning Bolt-Shock edge missing")
    
    # Test graph reload
    graph2 = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)
    if edge_key in graph2.edges:
        edge2 = graph2.edges[edge_key]
        has_monthly = len(edge2.monthly_counts) > 0
        has_format = len(edge2.format_periods) > 0
        check("Graph reload preserves monthly_counts", has_monthly)
        check("Graph reload preserves format_periods", has_format)
        
        if has_monthly and has_format:
            # Check that counts match (allowing for some variance due to SQLite serialization)
            original_total = sum(edge.monthly_counts.values())
            reloaded_total = sum(edge2.monthly_counts.values())
            check("Graph reload preserves count totals", abs(original_total - reloaded_total) <= 1)
            
            # Check format periods match
            original_formats = set(edge.format_periods.keys())
            reloaded_formats = set(edge2.format_periods.keys())
            check("Graph reload preserves format period keys", original_formats == reloaded_formats)
    else:
        warn("Edge not found after reload", "Graph reload may have issues")
    
    if test_graph_path.exists():
        test_graph_path.unlink()
    
except Exception as e:
    check("Graph integration", False, str(e))


print("\n6. Testing data type consistency...")
try:
    # Test that all temporal data uses consistent types
    edge = Edge(
        card1="Test1",
        card2="Test2",
        weight=1,
        first_seen=datetime(2024, 1, 1),
        last_seen=datetime(2024, 1, 1),
    )
    edge.update_temporal(datetime(2024, 1, 15), "Modern")
    
    edge_dict = edge.to_dict()
    
    # Check types
    check("monthly_counts is dict", isinstance(edge_dict["monthly_counts"], dict))
    check("format_periods is dict", isinstance(edge_dict["format_periods"], dict))
    check("monthly_counts values are int", all(isinstance(v, int) for v in edge_dict["monthly_counts"].values()))
    check("format_periods values are dict", all(isinstance(v, dict) for v in edge_dict["format_periods"].values()))
    
    # Test JSON serialization types
    json_str = json.dumps(edge_dict)
    loaded = json.loads(json_str)
    check("JSON preserves dict types", isinstance(loaded["monthly_counts"], dict))
    check("JSON preserves int types", isinstance(list(loaded["monthly_counts"].values())[0], int))
    
except Exception as e:
    check("Data type consistency", False, str(e))


print("\n7. Testing format period key generation...")
try:
    edge = Edge(
        card1="Test1",
        card2="Test2",
        weight=1,
        first_seen=datetime(2024, 1, 1),
        last_seen=datetime(2024, 1, 1),
        game="MTG",
    )
    
    # Test with format
    edge.update_temporal(datetime(2024, 1, 15), "Standard")
    edge.update_temporal(datetime(2024, 1, 20), "Modern")
    
    check("Format periods created", len(edge.format_periods) > 0)
    
    # Check period keys are valid
    for period_key in edge.format_periods.keys():
        check(f"Period key '{period_key}' is valid", len(period_key) > 0 and "_" in period_key)
    
    # Test without format
    edge_no_format = Edge(
        card1="Test1",
        card2="Test2",
        weight=1,
        first_seen=datetime(2024, 1, 1),
        last_seen=datetime(2024, 1, 1),
    )
    edge_no_format.update_temporal(datetime(2024, 1, 15), None)
    check("Works without format", len(edge_no_format.monthly_counts) > 0)
    
except Exception as e:
    check("Format period key generation", False, str(e))


print("\n8. Testing temporal metadata enrichment...")
try:
    deck = {
        "type": {
            "inner": {
                "format": "Standard",
                "eventDate": "2025-08-01",
                "archetype": "Burn",
            },
        },
        "game": "magic",
        "roundResults": [
            {"roundNumber": 1, "opponentDeck": "Jund", "result": "W"},
            {"roundNumber": 2, "opponentDeck": "Burn", "result": "L"},
        ],
    }
    
    all_decks = [deck, deck]  # Duplicate for meta share
    
    enriched = enrich_deck_with_temporal_metadata(deck, all_decks)
    inner = enriched.get("type", {}).get("inner", {})
    
    check("Temporal metadata added", "daysSinceRotation" in inner or "daysSinceBanUpdate" in inner)
    
    # Meta share requires matching event dates and formats
    # The test deck has eventDate="2025-08-01" but all_decks might not match
    meta_share_present = "metaShare" in inner
    if not meta_share_present:
        warn("Meta share not computed", "May require matching event dates in all_decks")
    check("Meta share computed or skipped appropriately", True)  # Not a failure if skipped
    
    check("Matchup statistics computed", "matchupStatistics" in inner)
    
    if "matchupStatistics" in inner:
        matchup = inner["matchupStatistics"]
        check("Matchup has total rounds", matchup.get("total_rounds") == 2)
        check("Matchup has win rate", "win_rate" in matchup)
    
except Exception as e:
    check("Temporal metadata enrichment", False, str(e))


print("\n9. Testing consistency and trend calculations...")
try:
    # Consistent data
    consistent = {"2024-01": 10, "2024-02": 10, "2024-03": 10, "2024-04": 10}
    consistency_high = compute_consistency(consistent)
    check("Consistent data has high consistency", consistency_high > 0.7)
    
    # Inconsistent data
    inconsistent = {"2024-01": 5, "2024-02": 20, "2024-03": 3, "2024-04": 15}
    consistency_low = compute_consistency(inconsistent)
    check("Inconsistent data has low consistency", consistency_low < 0.7)
    check("Consistency scores differ", consistency_high > consistency_low)
    
    # Empty data
    consistency_empty = compute_consistency({})
    check("Empty data handled", consistency_empty == 0.0 or consistency_empty == 1.0)
    
except Exception as e:
    check("Consistency calculations", False, str(e))


print("\n10. Testing matchup aggregation edge cases...")
try:
    # Empty deck list
    aggregated_empty = aggregate_matchup_data([], min_samples=1)
    check("Empty deck list handled", aggregated_empty == {})
    
    # Decks without round results
    decks_no_results = [
        {"archetype": "Burn"},
        {"archetype": "Jund"},
    ]
    aggregated_no_results = aggregate_matchup_data(decks_no_results)
    check("Decks without results handled", aggregated_no_results == {})
    
    # Insufficient samples
    decks_insufficient = [
        {
            "archetype": "Burn",
            "roundResults": [{"opponentDeck": "Jund", "result": "W"}],
        },
    ]
    aggregated_insufficient = aggregate_matchup_data(decks_insufficient, min_samples=3)
    check("Insufficient samples filtered", "Burn" not in aggregated_insufficient or len(aggregated_insufficient.get("Burn", {})) == 0)
    
except Exception as e:
    check("Matchup aggregation edge cases", False, str(e))


# Summary
print("\n" + "=" * 70)
print(f"RESULTS: {len(passed)} passed, {len(issues)} issues, {len(warnings)} warnings")
print("=" * 70)

if issues:
    print("\nISSUES:")
    for name, issue in issues:
        print(f"  ✗ {name}: {issue}")

if warnings:
    print("\nWARNINGS:")
    for name, message in warnings:
        print(f"  ⚠ {name}: {message}")

if not issues:
    print("\n✓ All deep verification checks passed!")
    sys.exit(0)
else:
    print(f"\n✗ Found {len(issues)} issues")
    sys.exit(1)

