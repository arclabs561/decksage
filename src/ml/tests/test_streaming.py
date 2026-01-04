#!/usr/bin/env python3
"""Test streaming loader for memory efficiency."""

from pathlib import Path

import pytest


try:
    from ..validation.validators.loader import iter_decks_validated, stream_decks_lenient
except ImportError:
    # loader module is optional
    iter_decks_validated = None
    stream_decks_lenient = None
    pytest.skip("validators.loader module not available", allow_module_level=True)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = PROJECT_ROOT / "src" / "backend" / "decks_hetero.jsonl"
FIXTURE_DATA = Path(__file__).parent / "fixtures" / "decks_export_hetero_small.jsonl"

DECKS_HETERO = DEFAULT_DATA if DEFAULT_DATA.exists() else FIXTURE_DATA


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="Data file not found")
def test_iter_decks_validated():
    """Test streaming validation iterator."""
    count = 0
    valid_count = 0

    for deck, result in iter_decks_validated(
        DECKS_HETERO,
        game="auto",
        check_legality=False,
    ):
        count += 1
        if deck is not None and result.is_valid:
            valid_count += 1

        if count >= 100:
            break

    assert count == 100
    assert valid_count > 0


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="Data file not found")
def test_stream_decks_lenient():
    """Test streaming convenience wrapper."""
    decks = []

    for deck in stream_decks_lenient(
        DECKS_HETERO,
        game="auto",
        check_legality=False,
    ):
        decks.append(deck)
        if len(decks) >= 100:
            break

    assert len(decks) == 100


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="Data file not found")
def test_streaming_vs_batch_same_results():
    """Verify streaming produces same results as batch loading."""
    from ..validation.validators.loader import load_decks_lenient

    # Batch load
    batch_decks = load_decks_lenient(
        DECKS_HETERO,
        game="auto",
        max_decks=100,
        verbose=False,
    )

    # Stream load
    stream_decks = []
    for deck in stream_decks_lenient(DECKS_HETERO, game="auto"):
        stream_decks.append(deck)
        if len(stream_decks) >= 100:
            break

    # Should have same deck IDs
    batch_ids = {d.deck_id for d in batch_decks}
    stream_ids = {d.deck_id for d in stream_decks}

    assert batch_ids == stream_ids
