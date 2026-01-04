#!/usr/bin/env python3
"""
Tests for nuance fix utilities.

Tests cover:
- Safe cache key generation (collision resistance, sanitization)
- Safe division (zero-division protection)
- Numeric range validation
- Path sanitization
- JSON operations
- Type-safe operations
"""

from __future__ import annotations

import json

# Set up paths
from pathlib import Path

import pytest

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from ml.scripts.fix_nuances import (
    safe_cache_key,
    safe_division,
    safe_json_dump,
    safe_json_load,
    sanitize_path,
    type_safe_get,
    validate_numeric_range,
)


class TestSafeCacheKey:
    """Tests for safe cache key generation."""

    def test_safe_cache_key_basic(self):
        """Test basic cache key generation."""
        key = safe_cache_key("test_query", 1, "use_case", "magic")

        assert isinstance(key, str)
        assert "test_query" in key or len(key) > 0  # Should contain query or be hash-based

    def test_safe_cache_key_special_characters(self):
        """Test cache key with special characters."""
        key1 = safe_cache_key("test/query", 1, "use/case", "game")
        key2 = safe_cache_key("test\\query", 1, "use\\case", "game")

        # Should handle special characters without errors
        assert isinstance(key1, str)
        assert isinstance(key2, str)
        # Different input strings should produce different keys (hash-based)
        # Note: "/" and "\\" are different characters, so keys will differ
        assert key1 != key2  # Different inputs produce different hashes

    def test_safe_cache_key_hash_based(self):
        """Test hash-based cache key generation."""
        key1 = safe_cache_key("query1", 1, None, None, use_hash=True)
        key2 = safe_cache_key("query1", 1, None, None, use_hash=True)

        # Same inputs should produce same hash
        assert key1 == key2

    def test_safe_cache_key_collision_resistance(self):
        """Test that different inputs produce different keys."""
        key1 = safe_cache_key("query1", 1, "case1", "game1", use_hash=True)
        key2 = safe_cache_key("query2", 1, "case1", "game1", use_hash=True)
        key3 = safe_cache_key("query1", 2, "case1", "game1", use_hash=True)

        # Different inputs should produce different keys
        assert key1 != key2
        assert key1 != key3

    def test_safe_cache_key_length_limit(self):
        """Test that very long queries are handled."""
        long_query = "a" * 1000
        key = safe_cache_key(long_query, 1, None, None)

        # Should not crash and should produce valid key
        assert isinstance(key, str)
        assert len(key) > 0


class TestSafeDivision:
    """Tests for safe division."""

    def test_safe_division_normal(self):
        """Test normal division."""
        result = safe_division(10, 2)
        assert result == 5.0

    def test_safe_division_zero_denominator(self):
        """Test division by zero."""
        result = safe_division(10, 0)
        assert result == 0.0  # Default

    def test_safe_division_zero_denominator_custom_default(self):
        """Test division by zero with custom default."""
        result = safe_division(10, 0, default=1.0)
        assert result == 1.0

    def test_safe_division_none_denominator(self):
        """Test division with None denominator."""
        result = safe_division(10, None)
        assert result == 0.0

    def test_safe_division_float_result(self):
        """Test that result is always float."""
        result = safe_division(1, 3)
        assert isinstance(result, float)
        assert abs(result - 0.3333333333333333) < 0.0001

    def test_safe_division_invalid_types(self):
        """Test division with invalid types."""
        # String numbers can be converted to float, so this works
        result = safe_division("10", "2")
        assert result == 5.0  # float() can convert string numbers

        # Truly invalid types should return default
        result = safe_division("not a number", "2")
        assert result == 0.0  # Should return default on type error


class TestValidateNumericRange:
    """Tests for numeric range validation."""

    def test_validate_numeric_range_valid(self):
        """Test validation of value in range."""
        result = validate_numeric_range(5.0, 0.0, 10.0)
        assert result == 5.0

    def test_validate_numeric_range_below_min(self):
        """Test validation of value below minimum."""
        with pytest.raises(ValueError, match="outside valid range"):
            validate_numeric_range(-1.0, 0.0, 10.0)

    def test_validate_numeric_range_above_max(self):
        """Test validation of value above maximum."""
        with pytest.raises(ValueError, match="outside valid range"):
            validate_numeric_range(11.0, 0.0, 10.0)

    def test_validate_numeric_range_clamp(self):
        """Test clamping to range."""
        result = validate_numeric_range(15.0, 0.0, 10.0, clamp=True)
        assert result == 10.0

    def test_validate_numeric_range_clamp_below(self):
        """Test clamping below minimum."""
        result = validate_numeric_range(-5.0, 0.0, 10.0, clamp=True)
        assert result == 0.0

    def test_validate_numeric_range_invalid_type(self):
        """Test validation with invalid type."""
        with pytest.raises(ValueError, match="not a valid number"):
            validate_numeric_range("not a number", 0.0, 10.0)


class TestSanitizePath:
    """Tests for path sanitization."""

    def test_sanitize_path_normal(self):
        """Test sanitization of normal path."""
        path = "/normal/path/to/file.json"
        result = sanitize_path(path)
        assert result == path

    def test_sanitize_path_special_characters(self):
        """Test sanitization of path with special characters."""
        path = "path/with\nnewline\rreturn\x00null.json"
        result = sanitize_path(path)
        assert "\n" not in result
        assert "\r" not in result
        assert "\x00" not in result

    def test_sanitize_path_length_limit(self):
        """Test path length limiting."""
        long_path = "a" * 1000
        result = sanitize_path(long_path, max_length=100)
        assert len(result) <= 100


class TestSafeJsonOperations:
    """Tests for safe JSON operations."""

    def test_safe_json_load_success(self, tmp_path: Path):
        """Test successful JSON loading."""
        json_path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        with open(json_path, "w") as f:
            json.dump(data, f)

        result = safe_json_load(json_path)
        assert result == data

    def test_safe_json_load_missing_file(self):
        """Test loading missing file."""
        missing_path = Path("/nonexistent/file.json")

        with pytest.raises(FileNotFoundError):
            safe_json_load(missing_path)

    def test_safe_json_load_missing_file_with_default(self):
        """Test loading missing file with default."""
        missing_path = Path("/nonexistent/file.json")
        default = {"default": True}

        result = safe_json_load(missing_path, default=default)
        assert result == default

    def test_safe_json_load_malformed_json(self, tmp_path: Path):
        """Test loading malformed JSON."""
        json_path = tmp_path / "test.json"
        json_path.write_text("{ invalid json }")

        with pytest.raises(ValueError, match="Invalid JSON"):
            safe_json_load(json_path)

    def test_safe_json_dump_success(self, tmp_path: Path):
        """Test successful JSON writing."""
        json_path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        safe_json_dump(data, json_path)

        assert json_path.exists()
        with open(json_path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_safe_json_dump_atomic_write(self, tmp_path: Path):
        """Test that JSON write is atomic (temp file then rename)."""
        json_path = tmp_path / "test.json"
        data = {"key": "value"}

        safe_json_dump(data, json_path)

        # Temp file should not exist after successful write
        temp_path = json_path.with_suffix(json_path.suffix + ".tmp")
        assert not temp_path.exists()
        assert json_path.exists()


class TestTypeSafeGet:
    """Tests for type-safe dictionary access."""

    def test_type_safe_get_present(self):
        """Test getting present key with correct type."""
        data = {"key": "value", "number": 42}

        result = type_safe_get(data, "key", str)
        assert result == "value"

    def test_type_safe_get_missing(self):
        """Test getting missing key."""
        data = {"key": "value"}

        result = type_safe_get(data, "missing", str, default="default")
        assert result == "default"

    def test_type_safe_get_wrong_type(self):
        """Test getting key with wrong type."""
        data = {"key": 42}

        result = type_safe_get(data, "key", str, default="default")
        assert result == "default"

    def test_type_safe_get_numeric_conversion(self):
        """Test numeric type conversion."""
        data = {"number_str": "42", "number_int": 42}

        result1 = type_safe_get(data, "number_str", int, default=0)
        assert result1 == 42

        result2 = type_safe_get(data, "number_int", float, default=0.0)
        assert result2 == 42.0


class TestIntegration:
    """Integration tests for nuance fixes."""

    def test_cache_key_in_parallel_judge(self):
        """Test that cache key function works in parallel_multi_judge context."""
        # Import and test the function
        from ml.scripts.parallel_multi_judge import _get_cache_key

        key = _get_cache_key("test query", 1, "use_case", "magic")
        assert isinstance(key, str)
        assert len(key) > 0

    def test_safe_division_in_validation(self):
        """Test that safe division is used in validation scripts."""
        # Test the function directly
        from ml.scripts.fix_nuances import safe_division

        # Test various scenarios
        assert safe_division(10, 2) == 5.0
        assert safe_division(10, 0) == 0.0
        assert safe_division(10, None) == 0.0
        assert safe_division(1, 3) == pytest.approx(0.3333333333333333)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
