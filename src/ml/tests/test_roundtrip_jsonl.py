#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def _decks_equal_normalized(a: dict, b: dict) -> bool:
    # Compare on key fields; ignore ordering of cards within partitions
    if a.get("format") != b.get("format"):
        return False
    if a.get("deck_id") != b.get("deck_id"):
        return False
    pa = {
        p["name"]: sorted([(c["name"], c["count"]) for c in p["cards"]])
        for p in a.get("partitions", [])
    }
    pb = {
        p["name"]: sorted([(c["name"], c["count"]) for c in p["cards"]])
        for p in b.get("partitions", [])
    }
    return pa == pb


def test_export_hetero_roundtrip_small():
    from ..validation.validators.loader import load_decks_validated

    fixture = Path(__file__).resolve().parent / "fixtures" / "decks_export_hetero_small.jsonl"
    # load_decks_validated returns a list directly, not an object with .decks attribute
    decks = load_decks_validated(fixture, game="auto", max_decks=10, collect_metrics=False)
    assert len(decks) >= 1

    # Round-trip: model_dump then re-validate -> equal normalized deck
    for d in decks:
        dd = d.model_dump()
        # Re-validate via strict constructor of the same class
        revalidated = type(d).model_validate(dd).model_dump()
        assert _decks_equal_normalized(dd, revalidated)
