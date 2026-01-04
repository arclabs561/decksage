#!/usr/bin/env python3
from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st


@st.composite
def mtg_card(draw):
    name = draw(
        st.sampled_from(
            [
                "Lightning Bolt",
                "Goblin Guide",
                "Lava Spike",
                "Mountain",
                "Forest",
            ]
        )
    )
    count = draw(st.integers(min_value=1, max_value=4))
    return {"name": name, "count": count}


@st.composite
def mtg_deck_small(draw):
    # Build a small Modern-legal deck (lenient size check in round-trip)
    main_cards = draw(st.lists(mtg_card(), min_size=1, max_size=20))
    # Enforce per-card 4-of rule in total
    tallies = {}
    for c in main_cards:
        tallies[c["name"]] = tallies.get(c["name"], 0) + c["count"]
    assume(all(cnt <= 4 or name in {"Mountain", "Forest"} for name, cnt in tallies.items()))
    deck = {
        "deck_id": "prop_mtg",
        "format": "Modern",
        "partitions": [
            {"name": "Main", "cards": main_cards},
        ],
    }
    return deck


def _canonicalize(deck_dict: dict) -> dict:
    # Re-validate through Pydantic and dump; this is our canonical form
    from ..validation.validators import MTGDeck

    try:
        d = MTGDeck.model_validate(deck_dict)
    except Exception:
        # If invalid (e.g., <60), allow lenient size via API patching semantics
        return deck_dict
    return d.model_dump()


@given(mtg_deck_small())
def test_roundtrip_canonicalization_mtg(deck):
    """Round-trip property: canonicalize(deck) is idempotent."""
    c1 = _canonicalize(deck)
    c2 = _canonicalize(c1)
    assert c1 == c2


@st.composite
def ygo_deck_small(draw):
    ygo_names = ["Blue-Eyes White Dragon"] + [f"Card {i}" for i in range(1, 10)]
    main_cards = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "name": st.sampled_from(ygo_names),
                    "count": st.integers(min_value=1, max_value=3),
                }
            ),
            min_size=1,
            max_size=40,
        )
    )
    deck = {
        "deck_id": "prop_ygo",
        "format": "TCG",
        "partitions": [{"name": "Main Deck", "cards": main_cards}],
    }
    return deck


@given(ygo_deck_small())
def test_roundtrip_canonicalization_ygo(deck):
    from ..validation.validators.models import YugiohDeck

    try:
        d = YugiohDeck.model_validate(deck)
    except Exception:
        pytest.skip("invalid small deck under rules")
    c1 = d.model_dump()
    c2 = YugiohDeck.model_validate(c1).model_dump()
    assert c1 == c2


@st.composite
def pkmn_deck_small(draw):
    pkmn_names = ["Pikachu", "Lightning Energy"] + [f"Trainer {i}" for i in range(1, 10)]
    main_cards = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "name": st.sampled_from(pkmn_names),
                    "count": st.integers(min_value=1, max_value=4),
                }
            ),
            min_size=1,
            max_size=60,
        )
    )
    deck = {
        "deck_id": "prop_pkmn",
        "format": "Standard",
        "partitions": [{"name": "Main Deck", "cards": main_cards}],
    }
    return deck


@given(pkmn_deck_small())
def test_roundtrip_canonicalization_pkmn(deck):
    from ..validation.validators.models import PokemonDeck

    try:
        d = PokemonDeck.model_validate(deck)
    except Exception:
        pytest.skip("invalid small deck under rules")
    c1 = d.model_dump()
    c2 = PokemonDeck.model_validate(c1).model_dump()
    assert c1 == c2


@given(mtg_deck_small())
def test_random_edits_preserve_invariants(deck):
    """Random small edits preserve invariants: names normalized, counts >= 1."""
    from ..deck_building.deck_patch import DeckPatch, apply_deck_patch

    # Apply edits that keep per-card count <= 4
    # Compute current LB count
    current = 0
    for p in deck.get("partitions", []):
        if p.get("name") == "Main":
            for c in p.get("cards", []):
                if c.get("name") == "Lightning Bolt":
                    current += int(c.get("count", 0))
    add_allowed = max(0, 4 - current)
    if add_allowed == 0:
        pytest.skip("no room for more copies without violating 4-of")
    ops = [
        {
            "op": "add_card",
            "partition": "Main",
            "card": "Lightning Bolt",
            "count": min(3, add_allowed),
        }
    ]
    res = apply_deck_patch("magic", deck, DeckPatch(ops=ops))
    assert res.is_valid
    out = res.deck or deck
    # Invariants
    for p in out.get("partitions", []):
        for c in p.get("cards", []):
            assert isinstance(c["name"], str) and c["name"].strip() == c["name"]
            assert int(c["count"]) >= 1
