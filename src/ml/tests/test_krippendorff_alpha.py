"""Tests for Krippendorff's Alpha calculation."""

from __future__ import annotations

import pytest

from ml.evaluation.krippendorff_alpha import compute_iaa_for_labels, krippendorff_alpha


def test_krippendorff_alpha_perfect_agreement():
    """Test alpha with perfect agreement."""
    data = [
        ["A", "B", "C"],
        ["A", "B", "C"],
        ["A", "B", "C"],
    ]
    alpha = krippendorff_alpha(data)
    assert alpha == pytest.approx(1.0, abs=0.01)


def test_krippendorff_alpha_no_agreement():
    """Test alpha with no agreement."""
    data = [
        ["A", "B", "C"],
        ["D", "E", "F"],
        ["G", "H", "I"],
    ]
    alpha = krippendorff_alpha(data)
    # Should be negative or very low
    assert alpha < 0.5


def test_krippendorff_alpha_partial_agreement():
    """Test alpha with partial agreement."""
    data = [
        ["A", "A", "B"],
        ["A", "A", "B"],
        ["A", "B", "B"],
    ]
    alpha = krippendorff_alpha(data)
    # Should be positive but less than 1.0
    assert 0.0 < alpha < 1.0


def test_compute_iaa_for_labels():
    """Test IAA computation for label judgments."""
    judgments = [
        {
            "highly_relevant": ["Card1", "Card2"],
            "relevant": ["Card3"],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        },
        {
            "highly_relevant": ["Card1"],
            "relevant": ["Card2", "Card3"],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        },
        {
            "highly_relevant": ["Card1", "Card2"],
            "relevant": ["Card3"],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        },
    ]
    
    iaa = compute_iaa_for_labels(judgments)
    
    assert iaa["num_judges"] == 3
    assert "krippendorff_alpha" in iaa
    assert "agreement_rate" in iaa
    assert "num_items" in iaa
    assert iaa["num_items"] == 3  # Card1, Card2, Card3


def test_compute_iaa_empty():
    """Test IAA computation with empty judgments."""
    iaa = compute_iaa_for_labels([])
    
    assert iaa["num_judges"] == 0
    assert iaa["krippendorff_alpha"] == 0.0
    assert iaa["agreement_rate"] == 0.0




