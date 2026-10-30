"""The simulation contract holds the same shape for every game."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.simulation import (
    BatchResult,
    DeckList,
    Game,
    Refusal,
    SimStatus,
    capabilities,
    for_game,
)


def deck(game: Game = Game.MAGIC, cards: dict[str, int] | None = None) -> DeckList:
    return DeckList(game=game, cards=cards or {"Lightning Bolt": 4, "Mountain": 56})


def test_every_game_resolves_to_an_adapter() -> None:
    for game in Game:
        sim = for_game(game)
        caps = sim.capabilities()
        assert caps.game is game
        assert caps.engine


def test_unavailable_adapters_refuse_with_a_reason() -> None:
    sim = for_game(Game.YUGIOH)
    try:
        sim.batch(deck(Game.YUGIOH), deck(Game.YUGIOH), games=1)
    except Refusal as exc:
        assert exc.reason
        assert exc.hint
    else:  # pragma: no cover - the adapter must not silently succeed
        raise AssertionError("Yu-Gi-Oh! adapter produced a result without an engine")


def test_batch_result_reports_rates_from_counts_not_guesswork() -> None:
    result = BatchResult(
        game=Game.MAGIC,
        deck_a=deck(),
        deck_b=deck(),
        games=10,
        wins_a=7,
        wins_b=2,
        draws=1,
        wall_ms=2000,
    )
    assert result.win_rate_a == 7 / 9  # draws excluded from the denominator
    assert result.games_per_second == 5.0
    payload = result.as_dict()
    assert payload["status"] == str(SimStatus.OK)
    assert payload["wins_a"] == 7


def test_deck_size_is_the_sum_of_counts() -> None:
    assert deck(cards={"A": 4, "B": 2}).size == 6


def test_capabilities_declare_licensing_and_addressing() -> None:
    caps = {c.game: c for c in capabilities()}
    assert caps[Game.MAGIC].addressable_by == "name"
    assert caps[Game.YUGIOH].licensed_for_service is False
    assert caps[Game.POKEMON].addressable_by == "card_id"
