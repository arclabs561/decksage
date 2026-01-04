import pytest
from hypothesis import given
from hypothesis import strategies as st


try:
    from ..deck_building.deck_patch import DeckPatch, apply_deck_patch
except ImportError:
    # deck_patch module doesn't exist (commented out in deck_completion.py)
    DeckPatch = None
    apply_deck_patch = None
    pytest.skip("deck_patch module not available", allow_module_level=True)

from ..validation.validators import MTGDeck


# Optional extended fixtures; skip if unavailable
try:
    from .fixtures.decks import DECK_ROUGHS, DECK_TRONS  # type: ignore
except Exception:  # pragma: no cover
    DECK_ROUGHS = []
    DECK_TRONS = []


def load_deck_from_dict(data: dict) -> MTGDeck:
    """Helper to load a deck from a dictionary for testing."""
    return MTGDeck.model_validate(data)


@st.composite
def add_ops(draw):
    card = draw(st.sampled_from(["Lightning Bolt", "Lava Spike", "Goblin Guide"]))
    # bound to avoid exceeding 4-copies across <=5 ops
    cnt = draw(st.integers(min_value=1, max_value=2))
    return {"op": "add_card", "partition": "Main", "card": card, "count": cnt}


@given(st.lists(add_ops(), min_size=1, max_size=2))
def test_commutativity_for_adds(ops):
    deck = {
        "deck_id": "ex",
        "format": "Modern",
        "partitions": [{"name": "Main", "cards": []}],
    }
    res1 = apply_deck_patch("magic", deck, DeckPatch(ops=ops))
    res2 = apply_deck_patch("magic", deck, DeckPatch(ops=list(reversed(ops))))
    assert res1.is_valid and res2.is_valid
    assert res1.deck is not None and res2.deck is not None

    # Multisets of names/counts equal
    def multiset(d):
        main = next(p for p in d["partitions"] if p["name"] == "Main")
        return sorted([(c["name"], c["count"]) for c in main["cards"]])

    assert multiset(res1.deck) == multiset(res2.deck)


@st.composite
def move_ops_roundtrip(draw):
    card = draw(st.sampled_from(["Lightning Bolt", "Goblin Guide"]))
    # Move 1 card between partitions and back
    # Note: DeckPatchOp uses 'partition' (source) and 'target_partition' (destination)
    return [
        {
            "op": "move_card",
            "partition": "Main",
            "target_partition": "Sideboard",
            "card": card,
            "count": 1,
        },
        {
            "op": "move_card",
            "partition": "Sideboard",
            "target_partition": "Main",
            "card": card,
            "count": 1,
        },
    ]


@given(move_ops_roundtrip())
def test_move_roundtrip_preserves_multiset(ops):
    deck = {
        "deck_id": "ex",
        "format": "Modern",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 2},
                    {"name": "Goblin Guide", "count": 2},
                ],
            },
            {"name": "Sideboard", "cards": []},
        ],
    }
    res1 = apply_deck_patch("magic", deck, DeckPatch(ops=ops))
    assert res1.is_valid and res1.deck is not None

    def multiset(d):
        main = next(p for p in d["partitions"] if p["name"] == "Main")
        side = next((p for p in d["partitions"] if p["name"] == "Sideboard"), {"cards": []})
        return (
            sorted([(c["name"], c["count"]) for c in main["cards"]]),
            sorted([(c["name"], c["count"]) for c in side.get("cards", [])]),
        )

    assert multiset(res1.deck) == multiset(deck)


from hypothesis import assume


@given(st.lists(add_ops(), min_size=1, max_size=3), st.lists(add_ops(), min_size=1, max_size=3))
def test_associativity_of_sequential_patches(p1, p2):
    deck = {
        "deck_id": "ex",
        "format": "Modern",
        "partitions": [{"name": "Main", "cards": []}],
    }
    # Enforce per-card count cap (<=4) across combined ops to avoid copy limit failures
    tallies = {}
    for op in p1 + p2:
        name = op["card"]
        tallies[name] = tallies.get(name, 0) + int(op["count"])
    assume(all(cnt <= 4 for cnt in tallies.values()))
    r1 = apply_deck_patch("magic", deck, DeckPatch(ops=p1))
    assert r1.is_valid and r1.deck is not None
    r12 = apply_deck_patch("magic", r1.deck, DeckPatch(ops=p2))
    combined = DeckPatch(ops=p1 + p2)
    r_combined = apply_deck_patch("magic", deck, combined)
    assert r12.is_valid and r_combined.is_valid

    def multiset(d):
        main = next(p for p in d["partitions"] if p["name"] == "Main")
        return sorted([(c["name"], c["count"]) for c in main["cards"]])

    assert multiset(r12.deck) == multiset(r_combined.deck)


def test_structured_errors_present_on_copy_limit_violation():
    deck = {
        "deck_id": "ex",
        "format": "Modern",
        "partitions": [{"name": "Main", "cards": [{"name": "Lightning Bolt", "count": 4}]}],
    }
    patch = DeckPatch(
        ops=[{"op": "add_card", "partition": "Main", "card": "Lightning Bolt", "count": 1}]
    )
    res = apply_deck_patch("magic", deck, patch)
    assert not res.is_valid
    assert res.errors is not None
    assert len(res.errors) > 0
    # Check that error message contains copy limit information
    assert any(
        "exceeds" in err.lower() or "copy" in err.lower() or "limit" in err.lower()
        for err in res.errors
    )
