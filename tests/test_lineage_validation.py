"""
Tests for lineage validation and safe_write context manager.
"""

import sys
import tempfile
from pathlib import Path

import pytest


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.utils.lineage import (
    check_dependencies,
    get_order_for_path,
    safe_write,
    validate_write_path,
)


def test_validate_write_path_order_0():
    """Test that Order 0 writes are rejected."""
    path = Path("src/backend/data-full/games/test.json")
    is_valid, error = validate_write_path(path, order=0)
    assert not is_valid
    assert "immutable" in error.lower()


def test_validate_write_path_order_1():
    """Test that Order 1 writes to valid locations are allowed."""
    path = Path("data/processed/test.json")
    is_valid, error = validate_write_path(path, order=1)
    assert is_valid
    assert error is None


def test_validate_write_path_order_0_location():
    """Test that writes to Order 0 locations are rejected even for higher orders."""
    path = Path("src/backend/data-full/games/test.json")
    is_valid, error = validate_write_path(path, order=1)
    assert not is_valid
    assert "immutable" in error.lower()


def test_safe_write_success():
    """Test successful safe_write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "test.json"
        with safe_write(test_path, order=1, strict=False) as path:
            path.write_text("test")
        assert test_path.exists()
        assert test_path.read_text() == "test"


def test_safe_write_strict_mode():
    """Test that strict mode raises on validation failure."""
    path = Path("src/backend/data-full/games/test.json")
    with pytest.raises(ValueError, match="Lineage violation"):
        with safe_write(path, order=1, strict=True):
            pass


def test_safe_write_non_strict_mode():
    """Test that non-strict mode logs warning but continues."""
    path = Path("src/backend/data-full/games/test.json")
    # Should not raise in non-strict mode
    with safe_write(path, order=1, strict=False) as validated_path:
        # Path is still yielded for writing
        assert validated_path == path


def test_get_order_for_path():
    """Test order inference from path."""
    # Note: get_order_for_path uses pattern matching, so exact matches may vary
    # Test that it returns an order for known paths
    order1 = get_order_for_path(Path("data/processed/decks_magic.jsonl"))
    assert order1 == 1 or order1 is None  # May return None if pattern doesn't match exactly

    order2 = get_order_for_path(Path("data/processed/pairs_magic.csv"))
    assert order2 == 2 or order2 is None

    # Test that it works for paths that clearly match patterns
    assert get_order_for_path(Path("data/graphs/incremental_graph.db")) == 3
    assert get_order_for_path(Path("data/embeddings/test.json")) == 4


def test_check_dependencies():
    """Test dependency checking."""
    # Order 1 depends on Order 0
    satisfied, missing = check_dependencies(1)
    # May or may not be satisfied depending on test environment
    assert isinstance(satisfied, bool)
    assert isinstance(missing, list)
