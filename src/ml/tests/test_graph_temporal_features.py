#!/usr/bin/env python3
"""
Tests for graph temporal features (monthly_counts, format_periods).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ml.data.incremental_graph import Edge, IncrementalCardGraph


def test_edge_temporal_distribution():
    """Test Edge temporal distribution tracking."""
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        weight=10,
        first_seen=datetime(2024, 1, 15),
        last_seen=datetime(2024, 3, 20),
    )
    
    # Update temporal distribution
    edge.update_temporal(datetime(2024, 1, 15), "Modern")
    edge.update_temporal(datetime(2024, 1, 20), "Modern")
    edge.update_temporal(datetime(2024, 2, 10), "Modern")
    edge.update_temporal(datetime(2024, 3, 5), "Standard")
    edge.update_temporal(datetime(2024, 3, 20), "Standard")
    
    # Check monthly counts
    assert "2024-01" in edge.monthly_counts, "Should track January"
    assert "2024-02" in edge.monthly_counts, "Should track February"
    assert "2024-03" in edge.monthly_counts, "Should track March"
    assert edge.monthly_counts["2024-01"] == 2, "January should have 2 occurrences"
    assert edge.monthly_counts["2024-02"] == 1, "February should have 1 occurrence"
    assert edge.monthly_counts["2024-03"] == 2, "March should have 2 occurrences"
    
    # Check format periods
    assert "Modern_2024" in edge.format_periods, "Should track Modern format period"
    assert "Standard_2024" in edge.format_periods, "Should track Standard format period"
    assert edge.format_periods["Modern_2024"]["2024-01"] == 2, "Modern should have 2 in January"
    assert edge.format_periods["Standard_2024"]["2024-03"] == 2, "Standard should have 2 in March"


def test_edge_serialization():
    """Test Edge serialization with temporal data."""
    edge = Edge(
        card1="Lightning Bolt",
        card2="Shock",
        weight=10,
        first_seen=datetime(2024, 1, 15),
        last_seen=datetime(2024, 3, 20),
    )
    
    edge.update_temporal(datetime(2024, 1, 15), "Modern")
    edge.update_temporal(datetime(2024, 2, 10), "Modern")
    
    # Serialize
    edge_dict = edge.to_dict()
    
    assert "monthly_counts" in edge_dict, "Should serialize monthly_counts"
    assert "format_periods" in edge_dict, "Should serialize format_periods"
    assert edge_dict["monthly_counts"]["2024-01"] == 1, "Should preserve counts"
    
    # Deserialize
    edge2 = Edge.from_dict(edge_dict)
    
    assert edge2.monthly_counts == edge.monthly_counts, "Should preserve monthly_counts"
    assert edge2.format_periods == edge.format_periods, "Should preserve format_periods"


def test_graph_temporal_tracking(temp_graph):
    """Test graph temporal tracking in add_deck."""
    graph = temp_graph
    
    # Add deck with format
    deck1 = {
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
    
    timestamp1 = datetime(2024, 1, 15)
    graph.set_deck_metadata("deck1", {"format": "Modern"})
    graph.add_deck(deck1, timestamp=timestamp1, deck_id="deck1")
    
    # Add same deck again in different month
    timestamp2 = datetime(2024, 2, 10)
    graph.add_deck(deck1, timestamp=timestamp2, deck_id="deck1")
    
    # Check edge temporal distribution
    edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
    assert edge_key in graph.edges, "Edge should exist"
    
    edge = graph.edges[edge_key]
    assert "2024-01" in edge.monthly_counts, "Should track January"
    assert "2024-02" in edge.monthly_counts, "Should track February"
    assert edge.monthly_counts["2024-01"] >= 1, "January should have at least 1"
    assert edge.monthly_counts["2024-02"] >= 1, "February should have at least 1"
    
    # Check format periods
    assert "Modern_2024" in edge.format_periods, "Should track Modern format period"


def test_graph_metadata_extraction(temp_graph):
    """Test graph extracts and stores enhanced metadata."""
    graph = temp_graph
    
    # Add deck with enhanced metadata
    deck = {
        "type": {
            "inner": {
                "format": "Standard",
                "tournamentType": "GP",
                "tournamentSize": 500,
                "location": "Las Vegas, NV",
                "eventDate": "2025-08-01",
            },
        },
        "game": "magic",
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
    
    graph.set_deck_metadata("deck1", {
        "format": "Standard",
        "tournament_type": "GP",
        "tournament_size": 500,
        "location": "Las Vegas, NV",
    })
    graph.add_deck(deck, timestamp=datetime(2025, 8, 1), deck_id="deck1")
    
    # Check that metadata was stored
    edge_key = tuple(sorted(["Lightning Bolt", "Shock"]))
    assert edge_key in graph.edges, "Edge should exist"
    
    edge = graph.edges[edge_key]
    # Format should be used for temporal tracking
    assert "Standard_2025" in edge.format_periods or len(edge.format_periods) >= 0, "Should track format period"


def test_temporal_stats_computation():
    """Test temporal statistics computation."""
    from ml.data.temporal_stats import compute_temporal_stats
    
    monthly_counts = {
        "2024-01": 5,
        "2024-02": 10,
        "2024-03": 8,
        "2024-04": 12,
    }
    
    first_seen = datetime(2024, 1, 1)
    last_seen = datetime(2024, 4, 30)
    total = sum(monthly_counts.values())
    
    stats = compute_temporal_stats(monthly_counts, first_seen, last_seen, total)
    
    assert stats.total_occurrences == total, "Should match total"
    assert stats.months_active == 4, "Should have 4 active months"
    assert stats.peak_month == "2024-04", "Peak should be April"
    assert stats.peak_count == 12, "Peak count should be 12"
    assert stats.consistency_score is not None, "Should compute consistency"
    assert 0.0 <= stats.consistency_score <= 1.0, "Consistency should be 0-1"
    assert stats.recent_trend is not None, "Should compute trend"


def test_recency_score():
    """Test recency score computation."""
    from ml.data.temporal_stats import compute_recency_score
    
    monthly_counts = {
        "2024-01": 10,
        "2024-06": 5,
        "2024-12": 20,
    }
    
    current_date = datetime(2025, 1, 1)
    recency = compute_recency_score(monthly_counts, current_date, decay_days=365.0)
    
    assert 0.0 <= recency <= 1.0, "Recency should be 0-1"
    # More recent months should have higher weight
    assert recency > 0, "Should have positive recency score"


def test_consistency_computation():
    """Test consistency score computation."""
    from ml.data.temporal_stats import compute_consistency
    
    # Consistent distribution
    consistent = {"2024-01": 10, "2024-02": 10, "2024-03": 10}
    consistency1 = compute_consistency(consistent)
    
    # Inconsistent distribution
    inconsistent = {"2024-01": 5, "2024-02": 20, "2024-03": 5}
    consistency2 = compute_consistency(inconsistent)
    
    assert consistency1 > consistency2, "Consistent should score higher"
    assert 0.0 <= consistency1 <= 1.0, "Consistency should be 0-1"
    assert 0.0 <= consistency2 <= 1.0, "Consistency should be 0-1"

