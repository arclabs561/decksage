from copy import deepcopy

import pytest

from ml.evaluation import deck_quality_validation as quality
from ml.utils.deck_parser import parse_deck_text


@pytest.mark.parametrize(
    "text",
    [
        "Deck\n56 Lightning Energy\n4 Pikachu",
        "Pokémon: 4\n4 Pikachu\nEnergy: 56\n56 Lightning Energy",
    ],
)
def test_completion_case_masks_physical_copies_and_checks_the_output(monkeypatch, text):
    deck = parse_deck_text(text, "pokemon")
    original = deepcopy(deck)
    monkeypatch.setattr(quality, "load_reference_decks", lambda *a, **kw: [deck])
    (case,) = quality.create_test_cases("pokemon", 1)
    assert deck == original
    assert case.target_size == 60
    assert sum(c["count"] for p in case.incomplete_deck["partitions"] for c in p["cards"]) == 45

    def run(output):
        monkeypatch.setattr(
            quality, "greedy_complete", lambda **kw: (output, [{"op": "add_card"}], None)
        )
        return quality.run_completion_test(
            case, lambda *_: [], lambda _: {"tag-a", "tag-b"}, lambda _: 2
        )

    assert run(parse_deck_text("Deck\n56 Lightning Energy\n4 Pikachu", "pokemon")).success
    for invalid in ["Deck\n57 Lightning Energy\n4 Pikachu", "Deck\n55 Lightning Energy\n5 Pikachu"]:
        bad = run(parse_deck_text(invalid, "pokemon"))
        assert not bad.success and bad.error
        assert bad.completed_deck == parse_deck_text(invalid, "pokemon")
