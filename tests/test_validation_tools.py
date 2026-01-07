#!/usr/bin/env python3
"""
Tests for validation tools.
"""

from pathlib import Path

import pytest

from scripts.validation.validate_evaluation_results import validate_evaluation_results
from scripts.validation.validate_test_set_quality import validate_test_set_quality


def test_validate_test_set_quality():
    """Test test set quality validation."""
    test_set = Path("experiments/test_set_canonical_magic_improved_fixed.json")
    if not test_set.exists():
        pytest.skip("Test set not found")

    result = validate_test_set_quality(test_set)
    assert "quality_score" in result
    assert result["quality_score"] >= 0.0
    assert result["quality_score"] <= 1.0


def test_validate_evaluation_results():
    """Test evaluation results validation."""
    results = Path("experiments/evaluation_results.json")
    if not results.exists():
        pytest.skip("Results file not found")

    result = validate_evaluation_results(results)
    assert "quality_score" in result
    assert isinstance(result["issues"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
