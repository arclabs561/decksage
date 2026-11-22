#!/usr/bin/env python3
"""Deck patches preserve stock, partitions, and untouched card data."""

from copy import deepcopy

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from ..deck_building.deck_patch import DeckPatch, apply_deck_patch


def make_deck(count):
    return {
        "deck_id": "example",
        "partitions": [
            {"name": "Main", "cards": [{"name": "Forest", "count": count, "set": "M10"}]}
        ],
    }


def operation(op, count=1, **fields):
    return {"op": op, "partition": "Main", "card": "Forest", "count": count, **fields}


def apply(deck, *ops, game="magic"):
    return apply_deck_patch(game, deck, DeckPatch(ops=ops))


@given(st.integers(1, 8), st.integers(1, 8))
def test_add_card_preserves_partition_structure(stock, count):
    deck = make_deck(stock)
    result = apply(deck, operation("add_card", count))
    assert result.is_valid
    assert result.deck == make_deck(stock + count)
    assert deck == make_deck(stock)


@given(st.integers(1, 8))
def test_empty_patch_preserves_deck(stock):
    result = apply(make_deck(stock))
    assert result.is_valid
    assert result.deck == make_deck(stock)


@given(st.integers(1, 8))
def test_remove_nonexistent_card_safe(stock):
    result = apply(make_deck(stock), operation("remove_card", card="Absent"))
    assert result.is_valid
    assert result.deck == make_deck(stock)


@given(st.integers(1, 8), st.integers(1, 8))
def test_move_uses_only_available_copies(stock, count):
    deck = make_deck(stock)
    result = apply(deck, operation("move_card", count, target_partition="Sideboard"))
    assert deck == make_deck(stock)
    if count > stock:
        assert not result.is_valid
        assert result.errors
        assert result.deck == deck
    else:
        assert result.is_valid
        main, side = result.deck["partitions"]
        assert main["cards"] == (
            [{"name": "Forest", "count": stock - count, "set": "M10"}] if stock > count else []
        )
        assert side == {
            "name": "Sideboard",
            "cards": [{"name": "Forest", "count": count, "set": "M10"}],
        }


def test_move_across_printings_merges_only_matching_metadata():
    deck = make_deck(1)
    deck["partitions"][0]["cards"].append({"name": "Forest", "count": 2, "set": "M11"})
    deck["partitions"].append(
        {"name": "Sideboard", "cards": [{"name": "Forest", "count": 1, "set": "M11"}]}
    )
    result = apply(deck, operation("move_card", 2, target_partition="Sideboard"))
    assert result.is_valid
    main, side = result.deck["partitions"]
    assert main["cards"] == [{"name": "Forest", "count": 1, "set": "M11"}]
    assert side["cards"] == [
        {"name": "Forest", "count": 2, "set": "M11"},
        {"name": "Forest", "count": 1, "set": "M10"},
    ]


def test_replace_only_requested_copies():
    result = apply(make_deck(4), operation("replace_card", 2, replacement_card="Island"))
    assert result.is_valid
    assert result.deck["partitions"][0]["cards"] == [
        {"name": "Forest", "count": 2, "set": "M10"},
        {"name": "Island", "count": 2},
    ]


@pytest.mark.parametrize(
    "bad",
    [
        operation("move_card"),
        operation("replace_card"),
        operation("replace_card", 4, replacement_card="Island"),
        operation("move_card", target_partition="Sideboard", partition="Missing"),
    ],
)
def test_impossible_operation_returns_original_deck(bad):
    deck = make_deck(1)
    before = deepcopy(deck)
    result = apply(deck, operation("add_card"), bad)
    assert not result.is_valid
    assert result.errors
    assert result.deck == deck == before


@pytest.mark.parametrize(
    "op", [operation("move_card", 0), operation("remove_card", -1), operation("typo")]
)
def test_invalid_operation_is_rejected(op):
    with pytest.raises(ValidationError):
        DeckPatch(ops=[op])


@pytest.mark.parametrize(("game", "limit"), [("magic", 4), ("pokemon", 4), ("yugioh", 3)])
def test_copy_limit_includes_every_partition(game, limit):
    deck = {
        "partitions": [
            {"name": name, "cards": [{"name": "Limited", "count": count}]}
            for name, count in [("Main", limit), ("Sideboard", 1)]
        ]
    }
    result = apply(deck, game=game)
    assert not result.is_valid
    assert f"{limit}-copy limit" in result.errors[0]
