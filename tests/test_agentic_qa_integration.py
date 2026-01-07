#!/usr/bin/env python3
"""
Integration tests for agentic QA system.

Tests the full workflow including agent initialization, tool usage,
and error handling.
"""

from __future__ import annotations

import pytest
import asyncio
import sqlite3
from pathlib import Path

from ml.qa.agentic_qa_tools import GraphQATools
from ml.utils.paths import PATHS


@pytest.mark.asyncio
async def test_agentic_tools_basic():
    """Test basic agentic tools functionality."""
    if not PATHS.incremental_graph_db.exists():
        pytest.skip("Graph database not available")
    
    tools = GraphQATools(PATHS.incremental_graph_db)
    
    # Test basic operations
    stats = tools.check_graph_statistics()
    assert isinstance(stats, dict)
    assert "nodes" in stats
    assert "edges" in stats
    
    integrity = tools.check_data_integrity()
    assert isinstance(integrity, dict)
    assert "integrity_score" in integrity
    assert 0.0 <= integrity["integrity_score"] <= 1.0
    
    tools.close()


@pytest.mark.asyncio
async def test_pipeline_summary():
    """Test pipeline summary generation."""
    if not PATHS.incremental_graph_db.exists():
        pytest.skip("Graph database not available")
    
    tools = GraphQATools(PATHS.incremental_graph_db)
    
    summary = tools.get_pipeline_summary()
    
    assert isinstance(summary, dict)
    assert "orders_with_data" in summary
    assert "orders_with_issues" in summary
    assert "total_orders" in summary
    
    tools.close()


@pytest.mark.asyncio
async def test_data_freshness_check():
    """Test data freshness checking."""
    if not PATHS.incremental_graph_db.exists():
        pytest.skip("Graph database not available")
    
    tools = GraphQATools(PATHS.incremental_graph_db)
    
    # Test freshness for each order
    for order in [0, 1, 2, 3, 4, 5, 6]:
        try:
            freshness = tools.check_data_freshness(order)
            assert isinstance(freshness, dict)
            assert "order" in freshness
            assert "is_fresh" in freshness
        except Exception as e:
            # Some orders may not have data, that's OK
            assert "error" in str(e).lower() or "missing" in str(e).lower()
    
    tools.close()


def test_tools_error_handling():
    """Test error handling in tools."""
    # Test with non-existent database
    fake_db = Path("/nonexistent/database.db")
    tools = GraphQATools(fake_db)
    
    # Should handle gracefully - either return error dict or raise
    try:
        stats = tools.check_graph_statistics()
        # If it doesn't raise, should return error dict
        assert isinstance(stats, dict), "Expected dict response"
        assert "error" in stats, "Expected error key in response"
    except Exception as e:
        # Raising is acceptable, but should be a specific exception type
        assert isinstance(e, (FileNotFoundError, sqlite3.OperationalError, ValueError)), \
            f"Expected specific exception type, got {type(e).__name__}"


@pytest.mark.asyncio
async def test_agentic_agent_initialization():
    """Test agentic agent can be initialized (if pydantic-ai available)."""
    try:
        from ml.qa.agentic_qa_agent import AgenticQAAgent
        
        if not PATHS.incremental_graph_db.exists():
            pytest.skip("Graph database not available")
        
        agent = AgenticQAAgent(graph_db=PATHS.incremental_graph_db)
        
        # Agent should be initialized
        assert agent.agent is not None
        assert agent.tools is not None
        
        agent.close()
    except ImportError:
        pytest.skip("pydantic-ai not available")


@pytest.mark.asyncio
async def test_agentic_analysis_fallback():
    """Test that fallback works when agent unavailable."""
    if not PATHS.incremental_graph_db.exists():
        pytest.skip("Graph database not available")
    
    tools = GraphQATools(PATHS.incremental_graph_db)
    
    # Should work without agent
    summary = tools.get_pipeline_summary()
    assert isinstance(summary, dict)
    
    integrity = tools.check_data_integrity()
    assert isinstance(integrity, dict)
    
    tools.close()

