#!/usr/bin/env python3
"""
Tests for standardized error messages.

Covers ErrorMessages class and get_error_message function.
"""

from __future__ import annotations

import pytest

from ..utils.error_messages import ErrorMessages, get_error_message


class TestErrorMessages:
    """Tests for ErrorMessages class."""

    def test_all_constants_exist(self):
        """Test that all expected error message constants exist."""
        expected = [
            "EMBEDDINGS_NOT_LOADED",
            "EMBEDDINGS_NOT_AVAILABLE",
            "CARD_NOT_IN_EMBEDDINGS",
            "GRAPH_NOT_LOADED",
            "GRAPH_NOT_AVAILABLE",
            "CARD_NOT_IN_GRAPH",
            "TAGGER_NOT_AVAILABLE",
            "TAGGER_LOAD_FAILED",
            "FUSION_NOT_AVAILABLE",
            "FUSION_LOAD_FAILED",
            "INVALID_FUSION_WEIGHTS",
            "DECK_NOT_FOUND",
            "DECK_INVALID",
            "DECK_EMPTY",
            "DECK_COMPLETION_FAILED",
            "DECK_PATCH_NOT_AVAILABLE",
            "VALIDATION_FAILED",
            "TEMPORAL_SPLIT_VIOLATION",
            "TEST_SET_TOO_SMALL",
            "TEST_SET_MALFORMED",
            "ASSETS_LOAD_FAILED",
            "EMBEDDINGS_LOAD_FAILED",
            "GRAPH_LOAD_FAILED",
            "TEXT_EMBEDDINGS_LOAD_FAILED",
            "GNN_EMBEDDINGS_LOAD_FAILED",
            "API_NOT_READY",
            "API_EMBEDDINGS_MISSING",
            "API_GRAPH_MISSING",
            "FILE_NOT_FOUND",
            "FILE_READ_ERROR",
            "FILE_WRITE_ERROR",
            "FILE_PERMISSION_ERROR",
            "DATA_LEAKAGE_DETECTED",
            "INVALID_DATA_FORMAT",
            "MISSING_REQUIRED_FIELD",
        ]

        for key in expected:
            assert hasattr(ErrorMessages, key), f"Missing error message constant: {key}"
            value = getattr(ErrorMessages, key)
            assert isinstance(value, str), f"Error message {key} should be string"
            assert len(value) > 0, f"Error message {key} should not be empty"

    def test_format_with_valid_key(self):
        """Test format() with valid error message key."""
        result = ErrorMessages.format("EMBEDDINGS_NOT_LOADED")
        assert result == "Embeddings not loaded"

    def test_format_with_template_string(self):
        """Test format() with template string (not a key)."""
        template = "Card {card} not found"
        result = ErrorMessages.format(template, card="Lightning Bolt")
        assert result == "Card Lightning Bolt not found"

    def test_format_with_invalid_key_returns_template(self):
        """Test format() with invalid key returns template as-is."""
        result = ErrorMessages.format("INVALID_KEY")
        assert result == "INVALID_KEY"

    def test_format_with_missing_kwargs(self):
        """Test format() with missing kwargs returns template as-is."""
        template = "Card {card} not found"
        result = ErrorMessages.format(template)
        # Should return template as-is when KeyError occurs
        assert result == template

    def test_format_with_extra_kwargs(self):
        """Test format() with extra kwargs (ignored)."""
        template = "Card {card} not found"
        result = ErrorMessages.format(template, card="Bolt", extra="ignored")
        assert result == "Card Bolt not found"

    def test_get_error_message_function(self):
        """Test get_error_message() helper function."""
        result = get_error_message("EMBEDDINGS_NOT_LOADED")
        assert result == "Embeddings not loaded"

    def test_get_error_message_with_kwargs(self):
        """Test get_error_message() with formatting kwargs."""
        # Use a template string since constants don't have placeholders
        result = get_error_message("Card {card} not found", card="Lightning Bolt")
        assert result == "Card Lightning Bolt not found"


