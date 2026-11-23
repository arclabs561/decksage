from copy import deepcopy

import pytest
from pydantic import ValidationError

from ..deck_building.deck_completion import CompletionConfig, greedy_complete
from ..deck_building.deck_patch import DeckPatch, apply_deck_patch
from ..validation.validators.models import MTGDeck, PokemonDeck, YugiohDeck


def part(name, *cards):
    return {"name": name, "cards": [{"name": card, "count": count} for card, count in cards]}


@pytest.mark.parametrize(
    "game,model,fmt,parts,valid",
    [
        (
            "magic",
            MTGDeck,
            "Modern",
            [part("Main", ("Island", 55), ("Persistent Petitioners", 5))],
            True,
        ),
        ("magic", MTGDeck, "Commander", [part("Main", ("Swamp", 91), ("Nazgûl", 9))], True),
        ("magic", MTGDeck, "Commander", [part("Main", ("Swamp", 90), ("Nazgûl", 10))], False),
        ("magic", MTGDeck, "cEDH", [part("Main", ("Forest", 99), ("Elf", 1))], True),
        ("magic", MTGDeck, "Commander", [part("Main", ("Forest", 98), ("Elf", 2))], False),
        (
            "magic",
            MTGDeck,
            "Brawl",
            [part("Main", ("Forest", 60)), part("Side", ("Island", 1))],
            False,
        ),
        (
            "magic",
            MTGDeck,
            "Modern",
            [part("Main", ("Forest", 30)), part("Mainboard", ("Island", 30))],
            True,
        ),
        ("magic", MTGDeck, "Commander", [part("Sideboard", ("Forest", 100))], False),
        ("magic", MTGDeck, "Modern", [part("Maindeck", ("Forest", 60))], True),
        ("pokemon", PokemonDeck, None, [part("Deck", ("Fire Energy", 56), ("X", 4))], True),
        (
            "pokemon",
            PokemonDeck,
            None,
            [part("Deck", ("Fire Energy", 55), ("Ｘ", 3), ("X", 2))],
            False,
        ),
        (
            "yugioh",
            YugiohDeck,
            None,
            [
                part("Main Deck", *((str(i), 1) for i in range(40))),
                part("Sideboard", *((str(i + 40), 1) for i in range(16))),
            ],
            False,
        ),
    ],
)
def test_strict_import_and_patch_agree(game, model, fmt, parts, valid):
    deck = {"deck_id": "fixture", "format": fmt, "partitions": parts}
    result = apply_deck_patch(game, deck, DeckPatch(ops=[]), lenient_size=False)
    assert result.is_valid is valid
    if valid:
        model.model_validate(deck)
    else:
        with pytest.raises(ValidationError) as exc:
            model.model_validate(deck)
        assert result.errors[0] in str(exc.value)


@pytest.mark.parametrize("failure", ["copy", "size", "operation", "legality"])
def test_failed_batch_returns_independent_original(failure, monkeypatch):
    from ..validation.validators import legality

    deck = {"partitions": [part("Main", ("Elf", 4))], "tags": ["fixture"]}
    before = deepcopy(deck)
    ops = [{"op": "add_card", "partition": "Main", "card": "Forest"}]
    if failure == "copy":
        ops.append({"op": "add_card", "partition": "Main", "card": "Elf"})
    if failure == "operation":
        ops.append(
            {"op": "move_card", "partition": "Main", "card": "Missing", "target_partition": "Side"}
        )
    monkeypatch.setattr(legality, "check_deck_legality", lambda *a, **kw: ["not legal"])
    result = apply_deck_patch(
        "magic",
        deck,
        DeckPatch.model_validate({"ops": ops}),
        lenient_size=failure != "size",
        check_legality=failure == "legality",
    )
    assert not result.is_valid and result.deck == before
    result.deck["tags"].append("changed")
    assert deck == before


def test_aliases_preserve_original_printings_during_move():
    main = part("Main", ("Elf", 1))
    main["cards"][0]["printing"] = "A"
    other = part("Mainboard", ("Elf", 1))
    other["cards"][0]["printing"] = "B"
    patch = DeckPatch.model_validate(
        {
            "ops": [
                {
                    "op": "move_card",
                    "partition": "Main Deck",
                    "card": "Elf",
                    "count": 2,
                    "target_partition": "Side",
                }
            ]
        }
    )
    result = apply_deck_patch("magic", {"partitions": [main, other]}, patch)
    assert result.is_valid
    a, b, side = result.deck["partitions"]
    assert not a["cards"] and not b["cards"]
    assert side["cards"] == main["cards"] + other["cards"]


def test_greedy_completion_fills_singleton_slots_one_card_at_a_time():
    deck = {"format": "commander", "partitions": [part("Mainboard", ("Forest", 98))]}

    def candidates(*_):
        return [("Elf", 1.0), ("Goblin", 0.9)]

    result, _, _ = greedy_complete(
        "magic", deck, candidates, CompletionConfig(game="magic", target_main_size=100)
    )
    assert len(result["partitions"]) == 1
    assert (
        result["partitions"][0]["cards"]
        == part("Main", ("Forest", 98), ("Elf", 1), ("Goblin", 1))["cards"]
    )


def test_legacy_request_keeps_format_and_rejects_duplicate():
    from ..api.deck_routes import deck_apply_patch
    from ..api.models import PatchRequest

    request = PatchRequest.model_validate(
        {
            "game": "magic",
            "deck": {"Main": ["Elf"], "format": "Commander"},
            "patch": {"ops": [{"op": "add_card", "partition": "Main", "card": "Elf"}]},
        }
    )
    result = deck_apply_patch(request)
    assert not result.is_valid
    assert result.deck == {"format": "Commander", "partitions": [part("Main", ("Elf", 1))]}


@pytest.mark.parametrize(
    "parts", [None, [None], [{"name": "Main", "cards": None}], [part("Main", ("Elf", -1))]]
)
def test_invalid_editor_rows_return_a_result(parts):
    deck = {"partitions": parts}
    result = apply_deck_patch("magic", deck, DeckPatch(ops=[]))
    assert result.deck == deck and not result.is_valid


def test_grouped_yugioh_import_and_edits_use_the_full_main_deck():
    parts = [
        part("Side Deck", ("Side card", 1)),
        part("Monsters", *((f"Monster {i}", 3) for i in range(8))),
        part("Spells", *((f"Spell {i}", 3) for i in range(5))),
        part("Traps", ("Trap", 1)),
    ]
    deck = {"deck_id": "grouped", "partitions": parts}
    edit = DeckPatch.model_validate(
        {"ops": [{"op": "add_card", "partition": "Traps", "card": "Trap"}]}
    )
    assert YugiohDeck.model_validate(deck).get_main_deck().name == "Monsters"
    result = apply_deck_patch("yugioh", deck, edit, lenient_size=False)
    assert result.is_valid
    assert result.deck["partitions"] == [*parts[:-1], part("Traps", ("Trap", 2))]

    short = {**deck, "partitions": parts[:-1]}
    rejected = apply_deck_patch("yugioh", short, DeckPatch(ops=[]), lenient_size=False)
    assert not rejected.is_valid and "(has 39)" in rejected.errors[0]


def test_maindeck_alias_is_recognized_with_sideboard_first():
    parts = [
        part("Sideboard", ("Elf", 1)),
        part("Maindeck", ("Forest", 30)),
        part("Main", ("Island", 30)),
    ]
    deck = {"deck_id": "split", "format": "Modern", "partitions": parts}
    model = MTGDeck.model_validate(deck)
    assert model.get_main_deck().name == "Maindeck"
    edit = DeckPatch.model_validate(
        {"ops": [{"op": "add_card", "partition": "Main", "card": "Forest"}]}
    )
    result = apply_deck_patch("magic", deck, edit, lenient_size=False)
    assert result.is_valid
    assert result.deck["partitions"] == [parts[0], part("Maindeck", ("Forest", 31)), parts[2]]
