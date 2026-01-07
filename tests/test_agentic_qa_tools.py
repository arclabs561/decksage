#!/usr/bin/env python3
"""
Tests for agentic QA tools.

Tests the underlying tools that the agent uses, ensuring they work correctly
and handle edge cases properly.
"""

from __future__ import annotations

import pytest
import sqlite3
import tempfile
from pathlib import Path

from ml.qa.agentic_qa_tools import GraphQATools
from ml.utils.paths import PATHS


@pytest.fixture
def temp_graph_db():
    """Create a temporary graph database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    # Create minimal test database
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE nodes (
            name TEXT PRIMARY KEY,
            game TEXT,
            first_seen TEXT,
            last_seen TEXT,
            total_decks INTEGER,
            attributes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE edges (
            card1 TEXT,
            card2 TEXT,
            weight REAL,
            game TEXT,
            metadata TEXT,
            FOREIGN KEY (card1) REFERENCES nodes(name),
            FOREIGN KEY (card2) REFERENCES nodes(name)
        )
    """)
    
    # Insert test data
    conn.execute("INSERT INTO nodes VALUES ('Lightning Bolt', 'MTG', '2024-01-01', '2024-01-01', 100, NULL)")
    conn.execute("INSERT INTO nodes VALUES ('Counterspell', 'MTG', '2024-01-01', '2024-01-01', 80, NULL)")
    conn.execute("INSERT INTO edges VALUES ('Lightning Bolt', 'Counterspell', 50.0, 'MTG', NULL)")
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    db_path.unlink()


def test_check_node_exists(temp_graph_db):
    """Test checking if a node exists."""
    tools = GraphQATools(temp_graph_db)
    
    # Existing node
    result = tools.check_node_exists("Lightning Bolt")
    assert result["exists"] is True
    assert result["game"] == "MTG"
    
    # Non-existent node
    result = tools.check_node_exists("Nonexistent Card")
    assert result["exists"] is False


def test_check_edge_exists(temp_graph_db):
    """Test checking if an edge exists."""
    tools = GraphQATools(temp_graph_db)
    
    # Existing edge
    result = tools.check_edge_exists("Lightning Bolt", "Counterspell")
    assert result["exists"] is True
    assert result["weight"] == 50.0
    
    # Non-existent edge
    result = tools.check_edge_exists("Lightning Bolt", "Brainstorm")
    assert result["exists"] is False


def test_check_data_integrity(temp_graph_db):
    """Test data integrity checking."""
    tools = GraphQATools(temp_graph_db)
    
    result = tools.check_data_integrity()
    
    assert "orphaned_edges" in result
    assert "integrity_score" in result
    assert "total_edges" in result
    assert result["integrity_score"] >= 0.0
    assert result["integrity_score"] <= 1.0


def test_check_graph_statistics(temp_graph_db):
    """Test graph statistics."""
    tools = GraphQATools(temp_graph_db)
    
    result = tools.check_graph_statistics()
    
    assert "nodes" in result
    assert "edges" in result
    assert result["nodes"]["total"] == 2
    assert result["edges"]["total"] == 1


def test_get_node_neighbors(temp_graph_db):
    """Test getting node neighbors."""
    tools = GraphQATools(temp_graph_db)
    
    neighbors = tools.get_node_neighbors("Lightning Bolt", limit=10)
    
    assert len(neighbors) == 1
    assert neighbors[0]["neighbor"] == "Counterspell"
    assert neighbors[0]["weight"] == 50.0


def test_sample_high_frequency_edges(temp_graph_db):
    """Test sampling high-frequency edges."""
    tools = GraphQATools(temp_graph_db)
    
    edges = tools.sample_high_frequency_edges(limit=10)
    
    assert len(edges) == 1
    assert edges[0]["card1"] == "Lightning Bolt"
    assert edges[0]["card2"] == "Counterspell"


def test_check_data_integrity_with_orphaned_edge(temp_graph_db):
    """Test integrity check with orphaned edge."""
    tools = GraphQATools(temp_graph_db)
    
    # Add orphaned edge (node doesn't exist)
    conn = sqlite3.connect(str(temp_graph_db))
    conn.execute("INSERT INTO edges VALUES ('Orphan', 'Card', 10.0, 'MTG', NULL)")
    conn.commit()
    conn.close()
    
    result = tools.check_data_integrity()
    
    assert result["orphaned_edges"] == 1
    assert result["integrity_score"] < 1.0


def test_tools_with_real_db():
    """Test tools with real database if available."""
    if not PATHS.incremental_graph_db.exists():
        pytest.skip("Real graph database not available")
    
    tools = GraphQATools(PATHS.incremental_graph_db)
    
    # Should not raise
    stats = tools.check_graph_statistics()
    assert "nodes" in stats
    assert "edges" in stats
    
    integrity = tools.check_data_integrity()
    assert "integrity_score" in integrity

