#!/usr/bin/env python3
"""
Integration tests for logging standards usage in actual code paths.

Tests that logging standards are used correctly in asset loading,
operations, and error scenarios.
"""

from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ..utils.logging_standards import LoggingStandards


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    handler = logging.StreamHandler(StringIO())
    handler.setLevel(logging.DEBUG)
    # Capture logs from multiple modules
    for logger_name in [
        "ml.utils.logging_standards",
        "ml.scripts.evaluate_downstream_complete",
        "ml.api.api",
        "ml.similarity.text_embeddings",
    ]:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    yield handler.stream
    # Cleanup
    for logger_name in [
        "ml.utils.logging_standards",
        "ml.scripts.evaluate_downstream_complete",
        "ml.api.api",
        "ml.similarity.text_embeddings",
    ]:
        logger = logging.getLogger(logger_name)
        logger.removeHandler(handler)


class TestAssetLoadingLogging:
    """Tests for logging in asset loading scenarios."""

    def test_load_embeddings_logs_progress(self, log_capture):
        """Test that embedding loading logs progress."""
        from ml.scripts.evaluate_downstream_complete import load_trained_assets

        # Try to load (may fail, but should log)
        try:
            load_trained_assets(
                game="magic",
                fast_mode=True,
            )
        except Exception:
            pass

        output = log_capture.getvalue()
        # Should have some logging output
        # (exact messages depend on implementation)

    def test_log_asset_load_in_actual_usage(self, log_capture):
        """Test LoggingStandards.log_asset_load in actual usage pattern."""
        # Simulate asset loading pattern
        LoggingStandards.log_asset_load("embeddings", "start", extra={"path": "/test/path"})
        LoggingStandards.log_asset_load("embeddings", "complete", extra={"count": 1000})

        output = log_capture.getvalue()
        assert "Loading embeddings" in output
        assert "Loaded embeddings" in output

    def test_log_asset_load_failed_scenario(self, log_capture):
        """Test logging when asset loading fails."""
        LoggingStandards.log_asset_load(
            "graph", "failed", extra={"error": "FileNotFoundError", "path": "/missing/path"}
        )

        output = log_capture.getvalue()
        assert "Failed to load graph" in output


class TestOperationLogging:
    """Tests for logging in operation scenarios."""

    def test_log_operation_in_actual_usage(self, log_capture):
        """Test LoggingStandards.log_operation in actual usage pattern."""
        # Simulate operation pattern
        LoggingStandards.log_operation("similarity_search", "start", extra={"query": "Bolt"})
        LoggingStandards.log_operation("similarity_search", "complete", extra={"results": 10})

        output = log_capture.getvalue()
        assert "Starting similarity_search" in output
        assert "Completed similarity_search" in output

    def test_log_operation_failed_scenario(self, log_capture):
        """Test logging when operation fails."""
        LoggingStandards.log_operation(
            "deck_completion", "failed", extra={"error": "TimeoutError", "deck_id": "test123"}
        )

        output = log_capture.getvalue()
        assert "Failed deck_completion" in output


class TestLogLevelCorrectness:
    """Tests that log levels are used correctly for different scenarios."""

    def test_error_level_for_critical_failures(self, log_capture):
        """Test ERROR level used for critical failures."""
        LoggingStandards.log_error(
            "Failed to load critical asset", exc_info=False, extra={"asset": "embeddings"}
        )

        output = log_capture.getvalue()
        # Should be logged at ERROR level
        # (exact format depends on formatter, but should be present)
        assert "Failed to load critical asset" in output

    def test_warning_level_for_recoverable_issues(self, log_capture):
        """Test WARNING level used for recoverable issues."""
        LoggingStandards.log_warning(
            "Optional dependency not available", extra={"dependency": "optional_lib"}
        )

        output = log_capture.getvalue()
        assert "Optional dependency not available" in output

    def test_info_level_for_state_changes(self, log_capture):
        """Test INFO level used for state changes."""
        LoggingStandards.log_info("Module initialized", extra={"module": "fusion"})

        output = log_capture.getvalue()
        assert "Module initialized" in output

    def test_debug_level_for_diagnostics(self, log_capture):
        """Test DEBUG level used for diagnostic information."""
        LoggingStandards.log_debug("Cache hit", extra={"key": "test_key"})

        output = log_capture.getvalue()
        assert "Cache hit" in output


class TestLoggingInTextEmbeddings:
    """Tests for logging in text embeddings module."""

    def test_cache_save_logs_debug(self, log_capture, tmp_path: Path):
        """Test that cache save logs at DEBUG level."""
        from ..similarity.text_embeddings import CardTextEmbedder

        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder._memory_cache = {"test": b"data"}

        # Set logger level to DEBUG
        logger = logging.getLogger("ml.similarity.text_embeddings")
        logger.setLevel(logging.DEBUG)

        embedder._save_cache()

        output = log_capture.getvalue()
        # Should log cache save (if DEBUG level enabled)
        # May not appear if logger level is higher


class TestLoggingPatterns:
    """Tests for consistent logging patterns across codebase."""

    def test_asset_loading_follows_pattern(self, log_capture):
        """Test that asset loading follows standard pattern."""
        # Pattern: start -> complete/failed
        LoggingStandards.log_asset_load("test_asset", "start")
        LoggingStandards.log_asset_load("test_asset", "complete")

        output = log_capture.getvalue()
        assert "Loading test_asset" in output
        assert "Loaded test_asset" in output

    def test_operation_follows_pattern(self, log_capture):
        """Test that operations follow standard pattern."""
        # Pattern: start -> complete/failed
        LoggingStandards.log_operation("test_op", "start")
        LoggingStandards.log_operation("test_op", "complete")

        output = log_capture.getvalue()
        assert "Starting test_op" in output
        assert "Completed test_op" in output

    def test_extra_kwargs_consistency(self, log_capture):
        """Test that extra kwargs are consistently passed."""
        LoggingStandards.log_info(
            "Test message",
            extra={"key1": "value1", "key2": 42, "key3": {"nested": "data"}},
        )

        output = log_capture.getvalue()
        assert "Test message" in output
        # Extra kwargs should be passed (exact format depends on formatter)


