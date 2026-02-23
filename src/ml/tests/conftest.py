"""Pytest configuration and shared fixtures for Tier 0 & Tier 1 tests."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

# Set up project paths
from ml.utils.path_setup import setup_project_paths


setup_project_paths()


@pytest.fixture(autouse=True)
def reset_api_state() -> None:
    """
    Reset global/per-process API state between tests.

    The FastAPI app and module-level caches are process globals; without an explicit
    reset, tests can leak state into each other (especially after multi-game changes).
    """
    try:
        import fastapi  # noqa: F401
    except ImportError:
        # If FastAPI isn't installed, API tests will be skipped anyway.
        return

    from ml.api import api as api_mod

    # Clear per-game state and caches.
    for attr in (
        "api_by_game",
        "search_by_game",
        "games",
        "default_game",
        "price_manager",
        "mtg_tagger",
    ):
        with suppress(Exception):
            delattr(api_mod.app.state, attr)

    # Clear legacy module-level globals used by _adopt_legacy_globals().
    api_mod.embeddings = None
    api_mod.graph_data = None
    api_mod.model_info = {}


@pytest.fixture
def temp_test_set(tmp_path: Path) -> Path:
    """Create a temporary test set file for testing."""
    test_set_path = tmp_path / "test_set.json"

    test_data = {
        "version": "test",
        "game": "magic",
        "queries": {
            f"query_{i}": {
                "highly_relevant": [f"card_{i}_1", f"card_{i}_2"],
                "relevant": [f"card_{i}_3"],
                "somewhat_relevant": [],
            }
            for i in range(100)
        },
    }

    with open(test_set_path, "w") as f:
        json.dump(test_data, f)

    return test_set_path


@pytest.fixture
def temp_decks_file(tmp_path: Path) -> Path:
    """Create a temporary decks file for testing."""
    decks_path = tmp_path / "decks.jsonl"

    decks = [
        {
            "source": "magic_tournament",
            "partitions": [
                {
                    "name": "Main",
                    "cards": [{"name": f"Card_{i}", "count": 4} for i in range(30)],
                }
            ],
        }
        for _ in range(20)
    ]

    with open(decks_path, "w") as f:
        for deck in decks:
            f.write(json.dumps(deck) + "\n")

    return decks_path


@pytest.fixture
def sample_deck() -> dict[str, Any]:
    """Create a sample deck for testing."""
    return {
        "source": "magic_tournament",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Rift Bolt", "count": 4},
                    {"name": "Lava Spike", "count": 4},
                    {"name": "Chain Lightning", "count": 4},
                    {"name": "Mountain", "count": 20},
                ],
            },
            {
                "name": "Sideboard",
                "cards": [
                    {"name": "Smash to Smithereens", "count": 3},
                ],
            },
        ],
    }


@pytest.fixture
def mock_fusion_system():
    """Create a mock fusion similarity system."""
    from unittest.mock import MagicMock

    mock_fusion = MagicMock()
    mock_fusion.similar = MagicMock(
        return_value=[
            ("Rift Bolt", 0.95),
            ("Chain Lightning", 0.90),
            ("Lava Spike", 0.85),
            ("Fireblast", 0.80),
            ("Lightning Strike", 0.75),
        ]
    )

    return mock_fusion


@pytest.fixture
def mock_tag_set_fn():
    """Create a mock functional tagger."""

    def tag_fn(card: str) -> set[str]:
        tags = {
            "Lightning Bolt": {"burn", "removal", "instant"},
            "Rift Bolt": {"burn", "sorcery"},
            "Lava Spike": {"burn", "sorcery"},
            "Chain Lightning": {"burn", "instant"},
            "Mountain": {"land", "basic"},
        }
        return tags.get(card, set())

    return tag_fn


@pytest.fixture
def mock_cmc_fn():
    """Create a mock CMC function."""

    def cmc_fn(card: str) -> int | None:
        cmcs = {
            "Lightning Bolt": 1,
            "Rift Bolt": 2,
            "Lava Spike": 1,
            "Chain Lightning": 2,
            "Mountain": 0,
        }
        return cmcs.get(card)

    return cmc_fn


@pytest.fixture()
def api_client(reset_api_state):
    """Create a test client for the API."""
    from fastapi.testclient import TestClient

    from ml.api.api import app

    return TestClient(app)


"""
Pytest configuration and fixtures.
"""


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
