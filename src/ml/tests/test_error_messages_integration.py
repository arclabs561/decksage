#!/usr/bin/env python3
"""
Integration tests for error message usage in actual code paths.

Tests that error messages are used correctly in API endpoints, validation,
and error handling scenarios.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ..utils.error_messages import ErrorMessages, get_error_message


class TestAPIErrorMessages:
    """Tests for error messages in API endpoints."""

    def test_api_ready_without_embeddings(self):
        """Test API ready endpoint uses error messages when embeddings missing."""
        from fastapi.testclient import TestClient

        from ..api.api import app, get_state

        # Reset state to ensure clean test
        state = get_state()
        state.embeddings = None
        state.graph_data = None
        state.model_info = {}

        client = TestClient(app)
        # /ready is at root level, not /v1/ready
        response = client.get("/ready")

        # Should return 503 when not ready
        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert "not ready" in data["detail"].lower() or "embeddings" in data["detail"].lower()

    def test_api_similar_without_embeddings(self):
        """Test API similar endpoint handles missing embeddings."""
        from fastapi.testclient import TestClient

        from ..api.api import app, get_state

        # Reset state
        state = get_state()
        state.embeddings = None
        state.graph_data = None

        client = TestClient(app)
        response = client.post("/v1/similar", json={"query": "Lightning Bolt", "top_k": 10})

        # Should return error (400, 503, 500, or 422 for validation)
        assert response.status_code in [400, 422, 503, 500]
        data = response.json()
        assert "error" in data or "detail" in data or "message" in data


class TestValidationErrorMessages:
    """Tests for error messages in validation functions."""

    def test_validate_deck_completion_error_format(self):
        """Test that validate_deck_completion returns properly formatted errors."""
        from ml.scripts.validate_deck_quality import validate_deck_completion

        # Test with invalid deck
        result = validate_deck_completion(
            incomplete_deck={"invalid": "structure"},
            game="magic",
            similarity_fn=lambda q, k: [],
            tag_set_fn=lambda c: set(),
            cmc_fn=lambda c: None,
        )

        if not result["success"]:
            assert "error" in result
            error_msg = result["error"]
            # Error should be a string
            assert isinstance(error_msg, str)
            assert len(error_msg) > 0


class TestAssetLoadingErrorMessages:
    """Tests for error messages in asset loading scenarios."""

    def test_load_embeddings_error_handling(self):
        """Test error handling when embeddings fail to load."""
        from pathlib import Path

        from ml.scripts.evaluate_downstream_complete import load_trained_assets

        # Try to load from non-existent path
        result = load_trained_assets(
            game="magic",
            embeddings_path=Path("/nonexistent/path/embeddings.wv"),
            fast_mode=True,
        )

        # Should handle gracefully
        assert "embeddings" in result
        # Embeddings should be None or error should be logged
        assert result.get("embeddings") is None or "error" in result


class TestErrorMessageConstants:
    """Tests that error message constants are used correctly."""

    def test_error_messages_are_strings(self):
        """Test all error message constants are strings."""
        for attr_name in dir(ErrorMessages):
            if not attr_name.startswith("_") and attr_name.isupper():
                value = getattr(ErrorMessages, attr_name)
                assert isinstance(value, str), f"{attr_name} should be string"
                assert len(value) > 0, f"{attr_name} should not be empty"

    def test_get_error_message_with_all_constants(self):
        """Test get_error_message works with all constants."""
        for attr_name in dir(ErrorMessages):
            if not attr_name.startswith("_") and attr_name.isupper():
                result = get_error_message(attr_name)
                assert isinstance(result, str)
                assert len(result) > 0

    def test_error_message_formatting_with_kwargs(self):
        """Test error message formatting with keyword arguments."""
        # Test with a template that has placeholders
        template = "Card {card} not found in {location}"
        result = ErrorMessages.format(template, card="Lightning Bolt", location="embeddings")
        assert "Lightning Bolt" in result
        assert "embeddings" in result

    def test_error_message_formatting_missing_kwargs(self):
        """Test error message formatting when kwargs are missing."""
        template = "Card {card} not found"
        # Missing 'card' kwarg
        result = ErrorMessages.format(template)
        # Should return template as-is when KeyError occurs
        assert result == template

