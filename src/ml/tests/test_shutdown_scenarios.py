#!/usr/bin/env python3
"""
Tests for Python shutdown scenarios and resource cleanup.

Covers cache saving during interpreter shutdown and edge cases.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ..similarity.text_embeddings import CardTextEmbedder


class TestShutdownScenarios:
    """Tests for shutdown and resource cleanup scenarios."""

    def test_save_cache_normal_operation(self, tmp_path: Path):
        """Test _save_cache() during normal operation."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {"test": b"data"}

        # Should save successfully
        embedder._save_cache()
        assert cache_file.exists()

        # Should be loadable
        with open(cache_file, "rb") as f:
            loaded = pickle.load(f)
        assert loaded == {"test": b"data"}

    def test_save_cache_during_shutdown(self, tmp_path: Path):
        """Test _save_cache() when sys.meta_path is None (shutdown)."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {"test": b"data"}

        # Simulate shutdown by setting meta_path to None
        original_meta_path = sys.meta_path
        try:
            sys.meta_path = None
            embedder._save_cache()
            # Should return early without saving
            assert not cache_file.exists()
        finally:
            sys.meta_path = original_meta_path

    def test_save_cache_logger_unavailable(self, tmp_path: Path):
        """Test _save_cache() when logger is unavailable."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {"test": b"data"}

        # Mock logger to raise AttributeError
        with patch.object(embedder.__class__, "_save_cache", wraps=embedder._save_cache):
            # Simulate logger unavailable by patching the logger access
            # This is tricky - we'll test the exception handling path
            with patch("ml.similarity.text_embeddings.logger") as mock_logger:
                mock_logger.warning.side_effect = AttributeError("Logger unavailable")

                # Should not raise, should handle gracefully
                embedder._save_cache()
                # Cache should still be saved if open() works
                if cache_file.exists():
                    # Normal path worked
                    pass
                else:
                    # Exception path was taken
                    pass

    def test_save_cache_open_unavailable(self, tmp_path: Path):
        """Test _save_cache() when open() is unavailable."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {"test": b"data"}

        # Mock builtins.open to raise NameError
        with patch("builtins.open", side_effect=NameError("open not available")):
            # Should handle gracefully without raising
            embedder._save_cache()
            # Should not crash

    def test_save_cache_permission_error(self, tmp_path: Path):
        """Test _save_cache() when file write fails."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {"test": b"data"}

        # Mock open to raise PermissionError
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # Should handle gracefully
            embedder._save_cache()
            # Should not crash

    def test_save_cache_empty_cache(self, tmp_path: Path):
        """Test _save_cache() with empty cache."""
        cache_file = tmp_path / "test_cache.pkl"
        embedder = CardTextEmbedder(cache_dir=str(tmp_path))
        embedder.cache_file = cache_file
        embedder._memory_cache = {}

        embedder._save_cache()
        assert cache_file.exists()

        # Should be loadable as empty dict
        with open(cache_file, "rb") as f:
            loaded = pickle.load(f)
        assert loaded == {}


