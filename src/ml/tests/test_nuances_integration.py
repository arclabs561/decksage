#!/usr/bin/env python3
"""
Integration tests for nuance fixes in actual usage contexts.

Tests that nuance fixes work correctly when used in real validation scripts.
"""

from __future__ import annotations

import json

# Set up paths
import sys
from pathlib import Path

import pytest

from ml.utils.path_setup import setup_project_paths


setup_project_paths()


class TestCacheKeyInParallelJudge:
    """Test cache key generation in parallel_multi_judge context."""

    def test_cache_key_special_characters(self):
        """Test that cache keys handle special characters correctly."""
        from ml.scripts.parallel_multi_judge import _get_cache_key

        # Test various special character scenarios
        test_cases = [
            ("normal query", 1, None, None),
            ("query/with/slashes", 1, "use/case", "game"),
            ("query\\with\\backslashes", 1, "use\\case", "game"),
            ("query:with:colons", 1, "use:case", "game"),
            ("query with spaces", 1, "use case", "game"),
            ("", 1, None, None),  # Empty query
        ]

        keys = []
        for query, judge_id, use_case, game in test_cases:
            key = _get_cache_key(query, judge_id, use_case, game)
            assert isinstance(key, str)
            assert len(key) > 0
            keys.append(key)

        # All keys should be unique
        assert len(set(keys)) == len(keys)

    def test_cache_key_collision_resistance(self):
        """Test that similar queries produce different keys."""
        from ml.scripts.parallel_multi_judge import _get_cache_key

        # Very similar queries should produce different keys
        key1 = _get_cache_key("query1", 1, None, None)
        key2 = _get_cache_key("query2", 1, None, None)
        key3 = _get_cache_key("query1", 2, None, None)  # Different judge

        assert key1 != key2
        assert key1 != key3


class TestSafeDivisionInValidation:
    """Test safe division in validation scripts."""

    def test_success_rate_calculation(self):
        """Test that success rate uses safe division."""
        from ml.scripts.fix_nuances import safe_division

        # Normal case
        assert safe_division(10, 20) == 0.5

        # Zero denominator
        assert safe_division(10, 0) == 0.0

        # None denominator
        assert safe_division(10, None) == 0.0

        # Empty results (would cause division by zero)
        assert safe_division(0, 0) == 0.0

    def test_quality_score_averages(self):
        """Test that quality score averages use safe division."""
        from ml.scripts.fix_nuances import safe_division

        # Normal case
        quality_scores = [7.5, 8.0, 6.5]
        avg = safe_division(sum(quality_scores), len(quality_scores))
        assert avg == pytest.approx(7.333333333333333)

        # Empty list (would cause division by zero)
        avg_empty = safe_division(sum([]), len([]))
        assert avg_empty == 0.0


class TestJsonOperationsInScripts:
    """Test safe JSON operations in validation scripts."""

    def test_safe_json_load_in_validation(self, tmp_path: Path):
        """Test that validation scripts use safe JSON loading."""
        from ml.scripts.fix_nuances import safe_json_load

        # Create test JSON
        json_path = tmp_path / "test.json"
        data = {"queries": {"q1": {"highly_relevant": ["c1"]}}}

        with open(json_path, "w") as f:
            json.dump(data, f)

        # Load should work
        loaded = safe_json_load(json_path)
        assert loaded == data

    def test_safe_json_load_malformed(self, tmp_path: Path):
        """Test safe JSON load with malformed JSON."""
        from ml.scripts.fix_nuances import safe_json_load

        json_path = tmp_path / "test.json"
        json_path.write_text("{ invalid json }")

        # Should return default or raise ValueError
        default = {}
        result = safe_json_load(json_path, default=default)
        assert result == default

    def test_safe_json_dump_atomic(self, tmp_path: Path):
        """Test that JSON writes are atomic."""
        from ml.scripts.fix_nuances import safe_json_dump

        json_path = tmp_path / "test.json"
        data = {"key": "value"}

        safe_json_dump(data, json_path)

        # File should exist and be valid
        assert json_path.exists()
        with open(json_path) as f:
            loaded = json.load(f)
        assert loaded == data

        # Temp file should not exist
        temp_path = json_path.with_suffix(json_path.suffix + ".tmp")
        assert not temp_path.exists()


class TestRandomSeedReproducibility:
    """Test random seed management for reproducibility."""

    def test_seed_reproducibility(self):
        """Test that same seed produces same results."""
        import random

        # Set seed
        random.seed(42)
        result1 = [random.randint(1, 100) for _ in range(10)]

        # Reset seed and generate again
        random.seed(42)
        result2 = [random.randint(1, 100) for _ in range(10)]

        # Should be identical
        assert result1 == result2

    def test_different_seeds_produce_different_results(self):
        """Test that different seeds produce different results."""
        import random

        random.seed(42)
        result1 = [random.randint(1, 100) for _ in range(10)]

        random.seed(43)
        result2 = [random.randint(1, 100) for _ in range(10)]

        # Should be different (very high probability)
        assert result1 != result2


class TestResourceCleanup:
    """Test resource cleanup in validation scripts."""

    def test_file_handles_closed(self, tmp_path: Path):
        """Test that file handles are properly closed."""
        from ml.scripts.fix_nuances import safe_json_dump, safe_json_load

        json_path = tmp_path / "test.json"
        data = {"key": "value"}

        # Write and read
        safe_json_dump(data, json_path)
        loaded = safe_json_load(json_path)

        # File should be readable (not locked)
        with open(json_path) as f:
            assert json.load(f) == data

    def test_subprocess_cleanup(self):
        """Test that subprocess cleanup works correctly."""
        import subprocess

        # Run a simple subprocess
        result = subprocess.run(
            [sys.executable, "-c", "print('test')"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        # Process should be cleaned up
        assert result.returncode == 0
        assert result.stdout.strip() == "test"


class TestPathSanitization:
    """Test path sanitization in various contexts."""

    def test_path_with_unicode(self):
        """Test path handling with unicode characters."""
        from ml.scripts.fix_nuances import sanitize_path

        unicode_path = "path/with/unicode/测试/文件.json"
        sanitized = sanitize_path(unicode_path)

        assert isinstance(sanitized, str)
        assert len(sanitized) > 0

    def test_path_with_special_characters(self):
        """Test path handling with special characters."""
        from ml.scripts.fix_nuances import sanitize_path

        special_path = "path/with\nnewline\rreturn\x00null.json"
        sanitized = sanitize_path(special_path)

        # Should remove problematic characters
        assert "\n" not in sanitized
        assert "\r" not in sanitized
        assert "\x00" not in sanitized


class TestTypeSafety:
    """Test type-safe operations."""

    def test_type_safe_get_in_validation(self):
        """Test type-safe dictionary access in validation contexts."""
        from ml.scripts.fix_nuances import type_safe_get

        # Test data with mixed types
        data = {
            "string_value": "test",
            "int_value": 42,
            "float_value": 3.14,
            "string_number": "123",
        }

        # Should get correct types
        assert type_safe_get(data, "string_value", str) == "test"
        assert type_safe_get(data, "int_value", int) == 42
        assert type_safe_get(data, "float_value", float) == 3.14

        # Should convert string numbers
        assert type_safe_get(data, "string_number", int, default=0) == 123

        # Should return default for wrong type
        assert type_safe_get(data, "string_value", int, default=0) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
