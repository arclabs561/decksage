#!/usr/bin/env python3
"""
Verification script for temporal enhancements.

Tests all new functionality without requiring pytest.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.data.format_events import get_format_events
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
)
from ml.utils.matchup_analysis import analyze_deck_matchups


print("=" * 70)
print("VERIFYING TEMPORAL ENHANCEMENTS")
print("=" * 70)

errors = []
passed = []


def test(name: str):
    """Decorator for test functions."""

    def decorator(func):
        def wrapper():
            try:
                func()
                passed.append(name)
                print(f"✓ {name}")
            except Exception as e:
                errors.append((name, str(e)))
                print(f"✗ {name}: {e}")

        return wrapper

    return decorator


@test("Edge temporal distribution tracking")
def test_edge_temporal():
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        weight=10,
        first_seen=datetime(2024, 1, 15),
        last_seen=datetime(2024, 3, 20),
    )

    edge.update_temporal(datetime(2024, 1, 15), "Modern")
    edge.update_temporal(datetime(2024, 1, 20), "Modern")
    edge.update_temporal(datetime(2024, 2, 10), "Modern")

    assert "2024-01" in edge.monthly_counts
    assert "2024-02" in edge.monthly_counts
    assert edge.monthly_counts["2024-01"] == 2
    assert "Modern_2024" in edge.format_periods


@test("Edge serialization with temporal data")
def test_edge_serialization():
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        weight=10,
        first_seen=datetime(2024, 1, 15),
        last_seen=datetime(2024, 3, 20),
    )

    edge.update_temporal(datetime(2024, 1, 15), "Modern")

    edge_dict = edge.to_dict()
    edge2 = Edge.from_dict(edge_dict)

    assert edge2.monthly_counts == edge.monthly_counts
    assert edge2.format_periods == edge.format_periods


@test("Days since rotation computation")
def test_days_since_rotation():
    days = compute_days_since_rotation("2025-08-01", "MTG", "Standard")
    assert days is not None
    assert days >= 0
    assert days < 365


@test("Days since ban update computation")
def test_days_since_ban():
    days = compute_days_since_ban_update("2025-08-01", "MTG", "Standard")
    # May be None if no bans, or a number
    assert days is None or days >= 0


@test("Format events database access")
def test_format_events():
    events = get_format_events("MTG", "Standard", end_date=datetime(2025, 8, 1))
    assert isinstance(events, list)


@test("Temporal statistics computation")
def test_temporal_stats():
    monthly_counts = {
        "2024-01": 5,
        "2024-02": 10,
        "2024-03": 8,
    }

    stats = compute_temporal_stats(
        monthly_counts,
        datetime(2024, 1, 1),
        datetime(2024, 3, 31),
        23,
    )

    assert stats.months_active == 3
    assert stats.peak_count == 10
    assert stats.consistency_score is not None


@test("Recency score computation")
def test_recency_score():
    monthly_counts = {
        "2024-01": 10,
        "2024-06": 5,
        "2024-12": 20,
    }

    recency = compute_recency_score(monthly_counts, datetime(2025, 1, 1), decay_days=365.0)
    assert 0.0 <= recency <= 1.0, f"Recency should be 0-1, got {recency}"
    # Recency is weighted average, should be positive if we have counts
    assert recency >= 0, f"Recency should be non-negative, got {recency}"


@test("Consistency computation")
def test_consistency():
    consistent = {"2024-01": 10, "2024-02": 10, "2024-03": 10}
    inconsistent = {"2024-01": 5, "2024-02": 20, "2024-03": 5}

    c1 = compute_consistency(consistent)
    c2 = compute_consistency(inconsistent)

    assert c1 > c2
    assert 0.0 <= c1 <= 1.0
    assert 0.0 <= c2 <= 1.0


@test("Matchup statistics computation")
def test_matchup_stats():
    deck = {
        "roundResults": [
            {"roundNumber": 1, "opponent": "Player 2", "opponentDeck": "Jund", "result": "W"},
            {"roundNumber": 2, "opponent": "Player 3", "opponentDeck": "Burn", "result": "L"},
            {"roundNumber": 3, "opponent": "Player 4", "opponentDeck": "Jund", "result": "W"},
        ],
    }

    stats = compute_matchup_statistics(deck)

    assert stats is not None
    assert stats["total_rounds"] == 3
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert abs(stats["win_rate"] - 2 / 3) < 0.01


@test("Matchup analysis")
def test_matchup_analysis():
    deck = {
        "archetype": "Burn",
        "roundResults": [
            {"roundNumber": 1, "opponent": "Player 2", "opponentDeck": "Jund", "result": "W"},
            {"roundNumber": 2, "opponent": "Player 3", "opponentDeck": "Burn", "result": "L"},
        ],
    }

    analysis = analyze_deck_matchups(deck)

    assert analysis["has_round_results"]
    assert analysis["total_rounds"] == 2


@test("Graph temporal tracking")
def test_graph_temporal():
    from ml.utils.paths import PATHS

    test_graph_path = PATHS.graphs / "test_verify_temporal.db"
    if test_graph_path.exists():
        test_graph_path.unlink()

    graph = IncrementalCardGraph(graph_path=test_graph_path, use_sqlite=True)

    deck = {
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
    }

    graph.set_deck_metadata("deck1", {"format": "Modern"})
    graph.add_deck(deck, timestamp=datetime(2024, 1, 15), deck_id="deck1")
    graph.add_deck(deck, timestamp=datetime(2024, 2, 10), deck_id="deck1")

    edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
    assert edge_key in graph.edges

    edge = graph.edges[edge_key]
    assert "2024-01" in edge.monthly_counts
    assert "2024-02" in edge.monthly_counts

    if test_graph_path.exists():
        test_graph_path.unlink()


def main():
    """Run all tests."""
    # Fix pytest.approx issue
    import sys

    if "pytest" not in sys.modules:
        # Simple approximation function
        def approx(value, abs=0.01):
            class Approx:
                def __init__(self, val, abs_tol):
                    self.val = val
                    self.abs_tol = abs_tol

                def __eq__(self, other):
                    return abs(self.val - other) <= self.abs_tol

            return Approx(value, abs)

        globals()["pytest"] = type("MockPytest", (), {"approx": approx})()

    print("\nRunning tests...\n")

    test_edge_temporal()
    test_edge_serialization()
    test_days_since_rotation()
    test_days_since_ban()
    test_format_events()
    test_temporal_stats()
    test_recency_score()
    test_consistency()
    test_matchup_stats()
    test_matchup_analysis()
    test_graph_temporal()

    print("\n" + "=" * 70)
    print(f"RESULTS: {len(passed)} passed, {len(errors)} failed")
    print("=" * 70)

    if errors:
        print("\nErrors:")
        for name, error in errors:
            print(f"  ✗ {name}: {error}")
        return 1

    print("\n✓ All tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
