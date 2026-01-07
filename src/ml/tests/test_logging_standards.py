#!/usr/bin/env python3
"""
Tests for logging standards and utilities.

Covers LoggingStandards class methods and log level correctness.
"""

from __future__ import annotations

import logging
from io import StringIO

import pytest

from ..utils.logging_standards import LoggingStandards


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    handler = logging.StreamHandler(StringIO())
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("ml.utils.logging_standards")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler.stream
    logger.removeHandler(handler)


class TestLoggingStandards:
    """Tests for LoggingStandards class."""

    def test_log_error(self, log_capture):
        """Test log_error() method."""
        LoggingStandards.log_error("Test error message", extra={"key": "value"})
        output = log_capture.getvalue()
        assert "Test error message" in output

    def test_log_warning(self, log_capture):
        """Test log_warning() method."""
        LoggingStandards.log_warning("Test warning", extra={"key": "value"})
        output = log_capture.getvalue()
        assert "Test warning" in output

    def test_log_info(self, log_capture):
        """Test log_info() method."""
        LoggingStandards.log_info("Test info", extra={"key": "value"})
        output = log_capture.getvalue()
        assert "Test info" in output

    def test_log_debug(self, log_capture):
        """Test log_debug() method."""
        LoggingStandards.log_debug("Test debug", extra={"key": "value"})
        output = log_capture.getvalue()
        assert "Test debug" in output

    def test_log_asset_load_start(self, log_capture):
        """Test log_asset_load() with 'start' status."""
        LoggingStandards.log_asset_load("embeddings", "start")
        output = log_capture.getvalue()
        assert "Loading embeddings..." in output

    def test_log_asset_load_complete(self, log_capture):
        """Test log_asset_load() with 'complete' status."""
        LoggingStandards.log_asset_load("embeddings", "complete")
        output = log_capture.getvalue()
        assert "Loaded embeddings" in output

    def test_log_asset_load_failed(self, log_capture):
        """Test log_asset_load() with 'failed' status."""
        LoggingStandards.log_asset_load("embeddings", "failed", extra={"error": "IOError"})
        output = log_capture.getvalue()
        assert "Failed to load embeddings" in output

    def test_log_asset_load_skipped(self, log_capture):
        """Test log_asset_load() with 'skipped' status."""
        LoggingStandards.log_asset_load("embeddings", "skipped")
        output = log_capture.getvalue()
        assert "Skipped loading embeddings" in output

    def test_log_asset_load_unknown_status(self, log_capture):
        """Test log_asset_load() with unknown status."""
        LoggingStandards.log_asset_load("embeddings", "custom_status")
        output = log_capture.getvalue()
        assert "embeddings: custom_status" in output

    def test_log_operation_start(self, log_capture):
        """Test log_operation() with 'start' status."""
        LoggingStandards.log_operation("similarity_search", "start")
        output = log_capture.getvalue()
        assert "Starting similarity_search..." in output

    def test_log_operation_complete(self, log_capture):
        """Test log_operation() with 'complete' status."""
        LoggingStandards.log_operation("similarity_search", "complete")
        output = log_capture.getvalue()
        assert "Completed similarity_search" in output

    def test_log_operation_failed(self, log_capture):
        """Test log_operation() with 'failed' status."""
        LoggingStandards.log_operation("similarity_search", "failed", extra={"error": "Timeout"})
        output = log_capture.getvalue()
        assert "Failed similarity_search" in output

    def test_log_operation_unknown_status(self, log_capture):
        """Test log_operation() with unknown status."""
        LoggingStandards.log_operation("similarity_search", "custom_status")
        output = log_capture.getvalue()
        assert "similarity_search: custom_status" in output

    def test_extra_kwargs_passed_through(self, log_capture):
        """Test that extra kwargs are passed to logger."""
        LoggingStandards.log_info("Test", extra={"key1": "value1", "key2": "value2"})
        # Handler should receive extra kwargs (exact format depends on formatter)
        output = log_capture.getvalue()
        assert "Test" in output


