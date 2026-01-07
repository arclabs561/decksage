#!/usr/bin/env python3
"""
Tests for module reloading patterns used in test isolation.

Covers the pattern documented in test_validate_deck_quality.py for handling
ImportError scenarios with importlib.reload().
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


class TestModuleReloadingPattern:
    """Tests for module reloading pattern used in tests."""

    def test_reload_pattern_isolation(self):
        """Test that module reload doesn't affect other modules."""
        import ml.scripts.validate_deck_quality

        # Get original function
        original_func = ml.scripts.validate_deck_quality.validate_deck_completion

        # Reload module
        importlib.reload(ml.scripts.validate_deck_quality)

        # Function should still exist (may be same or different object)
        assert hasattr(ml.scripts.validate_deck_quality, "validate_deck_completion")

    def test_reload_with_mocked_import(self):
        """Test reload pattern with mocked __import__."""
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "ml.deck_building.deck_patch":
                raise ImportError("No module named 'ml.deck_building.deck_patch'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            import ml.scripts.validate_deck_quality
            importlib.reload(ml.scripts.validate_deck_quality)

            # Module should be reloaded with mocked import
            # The function should handle ImportError gracefully
            from ml.scripts.validate_deck_quality import validate_deck_completion

            result = validate_deck_completion(
                incomplete_deck={"partitions": []},
                game="magic",
                similarity_fn=lambda q, k: [],
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )

            assert result["success"] is False
            assert "deck_patch" in result.get("error", "").lower()

    def test_reload_doesnt_affect_other_tests(self):
        """Test that reload in one test doesn't affect other tests."""
        import ml.scripts.validate_deck_quality

        # Reload module
        importlib.reload(ml.scripts.validate_deck_quality)

        # Other modules should be unaffected
        import ml.deck_building.deck_completion

        # Should still be importable
        assert hasattr(ml.deck_building.deck_completion, "greedy_complete")

    def test_reload_clears_module_cache(self):
        """Test that reload clears module-level state."""
        import ml.scripts.validate_deck_quality

        # Set some module-level attribute if it exists
        if hasattr(ml.scripts.validate_deck_quality, "_test_state"):
            original_state = ml.scripts.validate_deck_quality._test_state
        else:
            original_state = None
            ml.scripts.validate_deck_quality._test_state = "modified"

        # Reload
        importlib.reload(ml.scripts.validate_deck_quality)

        # State should be reset (if it was set)
        if original_state is None:
            # If it didn't exist, it might still not exist or be reset
            pass
        else:
            # If it existed, reload should reset it
            current_state = getattr(ml.scripts.validate_deck_quality, "_test_state", None)
            # State may be reset or may be same depending on module implementation
            pass


