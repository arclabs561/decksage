#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def _norm_parts(deck: dict) -> dict:
    return {p["name"]: sorted([(c["name"], c["count"]) for c in p["cards"]]) for p in deck.get("partitions", [])}


def test_collection_format_roundtrip_small():
    from ..validation.validators.loader import load_decks_validated

    fixture = Path(__file__).resolve().parent / "fixtures" / "decks_collection_small.jsonl"
    decks = load_decks_validated(fixture, game="auto", max_decks=10, collect_metrics=False).decks
    assert len(decks) >= 1

    for d in decks:
        dd = d.model_dump()
        revalidated = type(d).model_validate(dd).model_dump()
        assert _norm_parts(dd) == _norm_parts(revalidated)


