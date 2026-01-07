"""
Pytest configuration and fixtures.
"""

from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir():
    """Fixture for test data directory."""
    return Path(__file__).parent.parent / "experiments"


@pytest.fixture
def sample_test_set():
    """Fixture for sample test set."""
    return {
        "queries": {
            "Lightning Bolt": {
                "highly_relevant": ["Shock", "Bolt"],
                "relevant": ["Lightning Strike"],
                "somewhat_relevant": ["Lava Spike"],
                "marginally_relevant": [],
                "irrelevant": ["Counterspell"],
            }
        }
    }
