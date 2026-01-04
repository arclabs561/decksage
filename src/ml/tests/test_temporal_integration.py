"""Integration tests for temporal enhancements.

Tests that temporal data flows correctly through the entire pipeline:
1. Deck metadata extraction
2. Graph add_deck with metadata
3. Edge update_temporal calls
4. Format period tracking
5. SQLite persistence
6. Real-world deck structures
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from ml.data.incremental_graph import IncrementalCardGraph


@pytest.fixture
def temp_graph(tmp_path):
    """Create a temporary IncrementalCardGraph for testing."""
    graph_path = tmp_path / "test_graph.db"
    graph = IncrementalCardGraph(graph_path=str(graph_path), use_sqlite=True)
    yield graph
    # Cleanup: graph is automatically saved/closed


@pytest.fixture
def nested_deck():
    """Create a nested deck structure for testing."""
    return {
        "deck_id": "nested_test",
        "format": "Modern",
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


@pytest.fixture
def deck_with_round_results():
    """Create a deck with round results for testing."""
    return {
        "deck_id": "round_results_test",
        "format": "Modern",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                ],
            },
        ],
        "roundResults": [
            {"roundNumber": 1, "opponentDeck": "Jund", "result": "W"},
            {"roundNumber": 2, "opponentDeck": "Burn", "result": "L"},
        ],
    }


class TestDeckMetadataToTemporalTracking:
    """Test deck metadata → format → temporal tracking flow."""

    def test_metadata_extraction_and_temporal_tracking(self, temp_graph, nested_deck):
        """Test that deck metadata is extracted and used for temporal tracking."""
        deck_id = "test_deck_001"
        timestamp = datetime(2024, 6, 15)

        # Set metadata (as update_graph_incremental.py does)
        temp_graph.set_deck_metadata(
            deck_id,
            {
                "format": "Modern",
                "event_date": "2024-06-15",
                "tournament_type": "GP",
                "tournament_size": 500,
            },
        )

        # Add deck (should extract format from metadata and call update_temporal)
        deck = {
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
        temp_graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)

        # Verify edge has temporal data
        edge_key = tuple(sorted(["Lightning Bolt", "Lava Spike"]))
        assert edge_key in temp_graph.edges

        edge = temp_graph.edges[edge_key]
        assert "Modern" in str(edge.format_periods) or len(edge.format_periods) > 0
        assert "2024-06" in edge.monthly_counts
        assert len(edge.format_periods) > 0

        # Check format period structure
        for period_key, period_data in edge.format_periods.items():
            assert len(period_data) > 0
            assert "2024-06" in period_data

    def test_reload_preserves_temporal_data(self, temp_graph, nested_deck):
        """Test that reload preserves monthly_counts and format_periods."""
        deck_id = "test_deck_001"
        timestamp = datetime(2024, 6, 15)

        temp_graph.set_deck_metadata(deck_id, {"format": "Modern"})
        deck = {
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
        temp_graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)

        edge_key = tuple(sorted(["Lightning Bolt", "Lava Spike"]))
        original_edge = temp_graph.edges[edge_key]

        # Save and reload
        temp_graph.save()
        graph2 = IncrementalCardGraph(graph_path=temp_graph.graph_path, use_sqlite=True)

        assert edge_key in graph2.edges
        edge2 = graph2.edges[edge_key]
        assert "2024-06" in edge2.monthly_counts
        assert len(edge2.format_periods) > 0


class TestMultipleFormats:
    """Test multiple formats on same edge."""

    def test_multiple_formats_tracked(self, temp_graph):
        """Test that multiple formats are tracked separately."""
        base_date = datetime(2024, 1, 1)
        formats = ["Modern", "Standard", "Legacy"]

        for i, format_name in enumerate(formats):
            deck = {
                "partitions": [
                    {
                        "name": "Main",
                        "cards": [
                            {"name": "Lightning Bolt", "count": 4},
                            {"name": "Rift Bolt", "count": 4},
                        ],
                    },
                ],
            }
            deck_id = f"deck_{format_name}_{i}"
            timestamp = base_date + timedelta(days=i * 60)

            temp_graph.set_deck_metadata(deck_id, {"format": format_name})
            temp_graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)

        edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
        assert edge_key in temp_graph.edges

        edge = temp_graph.edges[edge_key]
        assert len(edge.format_periods) >= 3
        assert all(len(period) > 0 for period in edge.format_periods.values())

        # Check each format period
        format_names = set()
        for period_key in edge.format_periods.keys():
            if "Modern" in period_key:
                format_names.add("Modern")
            if "Standard" in period_key:
                format_names.add("Standard")
            if "Legacy" in period_key:
                format_names.add("Legacy")
        assert len(format_names) == 3


class TestTemporalAccumulation:
    """Test temporal accumulation across time."""

    def test_temporal_accumulation_works(self, temp_graph, sample_deck):
        """Test that temporal data accumulates across multiple months."""
        base_date = datetime(2024, 1, 15)

        for i in range(6):
            deck_id = f"accum_deck_{i}"
            timestamp = base_date + timedelta(days=i * 30)  # Monthly

            temp_graph.set_deck_metadata(deck_id, {"format": "Modern"})
            temp_graph.add_deck(sample_deck, timestamp=timestamp, deck_id=deck_id)

        edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
        assert edge_key in temp_graph.edges

        edge = temp_graph.edges[edge_key]
        assert len(edge.monthly_counts) >= 3
        assert sum(edge.monthly_counts.values()) >= 6


class TestEdgeCases:
    """Test edge cases in integration."""

    def test_deck_without_format(self, temp_graph):
        """Test that deck without format still tracks monthly_counts."""
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

    def test_deck_with_round_results(self, temp_graph, deck_with_round_results):
        """Test that deck with round results stores metadata correctly."""
        deck_id = "round_results_deck"
        temp_graph.set_deck_metadata(
            deck_id,
            {
                "format": "Modern",
                "round_results": deck_with_round_results["roundResults"],
            },
        )
        temp_graph.add_deck(
            deck_with_round_results, timestamp=datetime(2024, 1, 15), deck_id=deck_id
        )

        # Check that deck metadata was stored
        metadata = temp_graph._deck_metadata_cache.get(deck_id, {})
        assert "round_results" in metadata
        assert len(metadata["round_results"]) == 2

    def test_nested_structure(self, temp_graph, nested_deck):
        """Test that nested type.inner structure is handled correctly."""
        deck_id = "nested_deck_001"
        timestamp = datetime(2024, 8, 1)

        # Extract format (as update_graph_incremental.py does)
        format_value = nested_deck.get("format") or (
            nested_deck.get("type", {}).get("inner", {})
            if isinstance(nested_deck.get("type"), dict)
            else {}
        ).get("format")

        temp_graph.set_deck_metadata(
            deck_id,
            {
                "format": format_value,
                "event_date": nested_deck["type"]["inner"]["eventDate"],
            },
        )
        temp_graph.add_deck(nested_deck, timestamp=timestamp, deck_id=deck_id)

        edge_key = tuple(sorted(["Lightning Strike", "Shock"]))
        assert edge_key in temp_graph.edges

        edge = temp_graph.edges[edge_key]
        assert "2024-08" in edge.monthly_counts
        assert len(edge.format_periods) > 0
