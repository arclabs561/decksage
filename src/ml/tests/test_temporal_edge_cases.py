"""Tests for temporal enhancements edge cases and robustness.

Comprehensive edge case testing for:
- Edge serialization with temporal data
- Temporal statistics with edge cases
- Recency score computation
- Matchup statistics edge cases
- Graph integration edge cases
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from ml.data.incremental_graph import Edge, IncrementalCardGraph
from ml.data.temporal_stats import (
    compute_consistency,
    compute_recency_score,
    compute_temporal_stats,
)
from ml.scripts.compute_temporal_metadata import compute_matchup_statistics
from ml.utils.matchup_analysis import aggregate_matchup_data


@pytest.fixture
def sample_edge():
    """Create a sample Edge with temporal data for testing."""
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        game="magic",
        weight=10,
        first_seen=datetime(2024, 1, 1),
        last_seen=datetime(2024, 3, 15),
        monthly_counts={"2024-01": 5, "2024-02": 3, "2024-03": 2},
        format_periods={
            "Modern_2024-2025": {"2024-01": 3, "2024-02": 2, "2024-03": 1},
            "Standard_2024-2025": {"2024-01": 2, "2024-02": 1, "2024-03": 1},
        },
    )
    return edge


@pytest.fixture
def temp_graph(tmp_path):
    """Create a temporary IncrementalCardGraph for testing."""
    graph_path = tmp_path / "test_graph.db"
    graph = IncrementalCardGraph(graph_path=str(graph_path), use_sqlite=True)
    yield graph
    # Cleanup: graph is automatically saved/closed


class TestEdgeSerialization:
    """Test Edge serialization with temporal data."""

    def test_edge_serialization_includes_temporal_fields(self, sample_edge):
        """Test that Edge serialization includes monthly_counts and format_periods."""
        edge_dict = sample_edge.to_dict()

        assert "monthly_counts" in edge_dict
        assert "format_periods" in edge_dict
        assert len(edge_dict["monthly_counts"]) > 0
        assert len(edge_dict["format_periods"]) > 0

    def test_edge_deserialization_preserves_temporal_data(self, sample_edge):
        """Test that Edge deserialization preserves temporal data."""
        edge_dict = sample_edge.to_dict()
        edge2 = Edge.from_dict(edge_dict)

        assert edge2.monthly_counts == sample_edge.monthly_counts
        assert edge2.format_periods == sample_edge.format_periods
        assert edge2.game == sample_edge.game
        assert edge2.weight == sample_edge.weight

    def test_edge_json_round_trip(self, sample_edge):
        """Test Edge JSON serialization round-trip."""
        edge_dict = sample_edge.to_dict()
        json_str = json.dumps(edge_dict)
        edge_dict_loaded = json.loads(json_str)
        edge3 = Edge.from_dict(edge_dict_loaded)

        assert edge3.monthly_counts == sample_edge.monthly_counts
        assert edge3.format_periods == sample_edge.format_periods


class TestTemporalStatisticsEdgeCases:
    """Test temporal statistics with edge cases."""

    def test_empty_monthly_counts(self):
        """Test that empty monthly_counts is handled."""
        stats = compute_temporal_stats({}, datetime(2024, 1, 1), datetime(2024, 1, 1), 0)
        assert stats.months_active == 0

    def test_single_month(self):
        """Test that single month is handled."""
        stats = compute_temporal_stats(
            {"2024-01": 10},
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
            10,
        )
        assert stats.months_active == 1
        assert stats.peak_count == 10

    def test_sparse_data(self):
        """Test that sparse data (months far apart) is handled."""
        stats = compute_temporal_stats(
            {"2024-01": 1, "2024-12": 1},
            datetime(2024, 1, 1),
            datetime(2024, 12, 31),
            2,
        )
        assert stats.months_active == 2
        assert stats.activity_span_days > 300

    def test_invalid_month_keys(self):
        """Test that invalid month keys are skipped."""
        stats = compute_temporal_stats(
            {"2024-01": 5, "invalid": 3, "2024-13": 2},  # Invalid months
            datetime(2024, 1, 1),
            datetime(2024, 12, 31),
            10,
        )
        assert stats.months_active >= 1


class TestRecencyScoreEdgeCases:
    """Test recency score edge cases."""

    def test_old_data_has_low_recency(self):
        """Test that old data (5 years ago) has low recency."""
        recency_old = compute_recency_score(
            {"2020-01": 100},
            datetime(2025, 1, 1),
            decay_days=365.0,
        )
        assert 0.0 <= recency_old <= 1.0
        assert recency_old < 0.1  # Should be very low

    def test_recent_data_has_high_recency(self):
        """Test that recent data (1 month ago) has high recency."""
        recency_recent = compute_recency_score(
            {"2024-12": 100},
            datetime(2025, 1, 1),
            decay_days=365.0,
        )
        assert 0.0 <= recency_recent <= 1.0
        assert recency_recent > 0.5  # Should be high

    def test_mixed_data_recency(self):
        """Test that mixed old and recent data has middle recency."""
        recency_old = compute_recency_score(
            {"2020-01": 100},
            datetime(2025, 1, 1),
            decay_days=365.0,
        )
        recency_recent = compute_recency_score(
            {"2024-12": 100},
            datetime(2025, 1, 1),
            decay_days=365.0,
        )
        recency_mixed = compute_recency_score(
            {"2020-01": 50, "2024-12": 50},
            datetime(2025, 1, 1),
            decay_days=365.0,
        )

        assert 0.0 < recency_mixed < 1.0
        assert recency_old < recency_mixed < recency_recent

    def test_zero_decay_days(self):
        """Test that zero decay days defaults correctly."""
        recency = compute_recency_score(
            {"2024-12": 10},
            datetime(2025, 1, 1),
            decay_days=0.0,  # Invalid, should default
        )
        assert recency >= 0.0

    def test_negative_counts_skipped(self):
        """Test that negative counts are skipped."""
        recency = compute_recency_score(
            {"2024-01": 10, "2024-02": -5},  # Negative count
            datetime(2025, 1, 1),
            decay_days=365.0,
        )
        assert recency >= 0.0


class TestMatchupStatisticsEdgeCases:
    """Test matchup statistics edge cases."""

    def test_empty_round_results(self):
        """Test that empty round results returns None."""
        deck = {"roundResults": []}
        stats = compute_matchup_statistics(deck)
        assert stats is None

    def test_invalid_results_filtered(self):
        """Test that invalid results are filtered."""
        deck = {"roundResults": [{"result": "INVALID"}, {"result": "W"}]}
        stats = compute_matchup_statistics(deck)
        assert stats is not None
        assert stats["total_rounds"] == 1

    def test_missing_opponent_archetypes(self):
        """Test that missing opponent archetypes are handled."""
        deck = {
            "roundResults": [
                {"roundNumber": 1, "opponent": "Player1", "result": "W"},
                {"roundNumber": 2, "opponent": "Player2", "result": "L"},
            ]
        }
        stats = compute_matchup_statistics(deck)
        assert stats is not None
        assert stats["win_rate"] == 0.5

    def test_all_ties(self):
        """Test that all ties are handled correctly."""
        deck = {
            "roundResults": [
                {"roundNumber": 1, "opponentDeck": "Jund", "result": "T"},
                {"roundNumber": 2, "opponentDeck": "Burn", "result": "T"},
            ]
        }
        stats = compute_matchup_statistics(deck)
        assert stats is not None
        assert stats["win_rate"] == 0.0
        assert stats["ties"] == 2


class TestGraphIntegrationEdgeCases:
    """Test graph integration with temporal data edge cases."""

    def test_graph_temporal_accumulation(self, temp_graph, sample_deck):
        """Test that temporal data accumulates across multiple decks."""
        base_date = datetime(2024, 1, 1)
        # Ensure sample_deck has format
        deck_with_format = sample_deck.copy()
        if "format" not in deck_with_format:
            deck_with_format["format"] = "Modern"

        for i in range(10):
            deck_id = f"deep_verify_deck_{i}"
            timestamp = base_date + timedelta(days=i * 30)

            temp_graph.set_deck_metadata(
                deck_id, {"format": deck_with_format.get("format", "Modern")}
            )
            temp_graph.add_deck(deck_with_format, timestamp=timestamp, deck_id=deck_id)

        # Check for an edge that exists in sample_deck (e.g., Lightning Bolt and Rift Bolt)
        edge_key = tuple(sorted(["Lightning Bolt", "Rift Bolt"]))
        assert edge_key in temp_graph.edges, (
            f"Edge {edge_key} not found. Available edges: {list(temp_graph.edges.keys())[:5]}"
        )

        edge = temp_graph.edges[edge_key]
        assert len(edge.monthly_counts) > 0
        assert len(edge.format_periods) > 0

        total_count = sum(edge.monthly_counts.values())
        assert total_count >= 10

    def test_graph_reload_preserves_temporal_data(self, temp_graph, sample_deck):
        """Test that graph reload preserves temporal data."""
        # Ensure sample_deck has format
        deck_with_format = sample_deck.copy()
        if "format" not in deck_with_format:
            deck_with_format["format"] = "Modern"

        # Add deck
        temp_graph.set_deck_metadata("deck1", {"format": deck_with_format.get("format", "Modern")})
        temp_graph.add_deck(deck_with_format, timestamp=datetime(2024, 1, 15), deck_id="deck1")

        # Check for an edge that exists in sample_deck (e.g., Lightning Bolt and Rift Bolt)
        edge_key = tuple(sorted(["Lightning Bolt", "Rift Bolt"]))
        assert edge_key in temp_graph.edges
        original_edge = temp_graph.edges[edge_key]
        original_monthly = original_edge.monthly_counts.copy()
        original_formats = original_edge.format_periods.copy()

        # Save and reload
        temp_graph.save()
        graph2 = IncrementalCardGraph(graph_path=temp_graph.graph_path, use_sqlite=True)

        assert edge_key in graph2.edges
        edge2 = graph2.edges[edge_key]
        assert len(edge2.monthly_counts) > 0
        assert len(edge2.format_periods) > 0
        assert edge2.monthly_counts == original_monthly
        assert edge2.format_periods == original_formats

    def test_graph_works_without_format(self, temp_graph):
        """Test that graph works without format metadata."""
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

        temp_graph.add_deck(deck, timestamp=datetime(2024, 1, 15), deck_id="no_format_deck")

        edge_key = tuple(sorted(["Card X", "Card Y"]))
        assert edge_key in temp_graph.edges

        edge = temp_graph.edges[edge_key]
        assert len(edge.monthly_counts) > 0
        assert "2024-01" in edge.monthly_counts


class TestDataTypeConsistency:
    """Test data type consistency for temporal data."""

    def test_monthly_counts_type(self, sample_edge):
        """Test that monthly_counts has correct types."""
        edge_dict = sample_edge.to_dict()

        assert isinstance(edge_dict["monthly_counts"], dict)
        assert all(isinstance(v, int) for v in edge_dict["monthly_counts"].values())

    def test_format_periods_type(self, sample_edge):
        """Test that format_periods has correct types."""
        edge_dict = sample_edge.to_dict()

        assert isinstance(edge_dict["format_periods"], dict)
        assert all(isinstance(v, dict) for v in edge_dict["format_periods"].values())

    def test_json_preserves_types(self, sample_edge):
        """Test that JSON serialization preserves types."""
        edge_dict = sample_edge.to_dict()
        json_str = json.dumps(edge_dict)
        loaded = json.loads(json_str)

        assert isinstance(loaded["monthly_counts"], dict)
        assert isinstance(list(loaded["monthly_counts"].values())[0], int)


class TestConsistencyCalculations:
    """Test consistency and trend calculations."""

    def test_consistent_data_has_high_consistency(self):
        """Test that consistent data has high consistency score."""
        consistent = {"2024-01": 10, "2024-02": 10, "2024-03": 10, "2024-04": 10}
        consistency_high = compute_consistency(consistent)
        assert consistency_high > 0.7

    def test_inconsistent_data_has_low_consistency(self):
        """Test that inconsistent data has low consistency score."""
        inconsistent = {"2024-01": 5, "2024-02": 20, "2024-03": 3, "2024-04": 15}
        consistency_low = compute_consistency(inconsistent)
        assert consistency_low < 0.7

    def test_consistency_scores_differ(self):
        """Test that consistency scores differ for different data."""
        consistent = {"2024-01": 10, "2024-02": 10, "2024-03": 10, "2024-04": 10}
        inconsistent = {"2024-01": 5, "2024-02": 20, "2024-03": 3, "2024-04": 15}

        consistency_high = compute_consistency(consistent)
        consistency_low = compute_consistency(inconsistent)

        assert consistency_high > consistency_low

    def test_empty_data_handled(self):
        """Test that empty data is handled."""
        consistency = compute_consistency({})
        assert consistency == 0.0 or consistency == 1.0


class TestMatchupAggregationEdgeCases:
    """Test matchup aggregation edge cases."""

    def test_empty_deck_list(self):
        """Test that empty deck list is handled."""
        aggregated = aggregate_matchup_data([], min_samples=1)
        assert aggregated == {}

    def test_decks_without_results(self):
        """Test that decks without round results are handled."""
        decks = [
            {"archetype": "Burn"},
            {"archetype": "Jund"},
        ]
        aggregated = aggregate_matchup_data(decks)
        assert aggregated == {}

    def test_insufficient_samples(self):
        """Test that insufficient samples are filtered."""
        decks = [
            {
                "archetype": "Burn",
                "roundResults": [{"opponentDeck": "Jund", "result": "W"}],
            },
        ]
        aggregated = aggregate_matchup_data(decks, min_samples=3)
        assert "Burn" not in aggregated or len(aggregated.get("Burn", {})) == 0
