"""Per-game simulators behind one contract.

Each game needs its own engine, and each engine is at a different stage of
readiness. That is the reality this package encodes: a shared type system
(`contract`), one adapter per game, and a registry that refuses loudly instead
of returning a number nobody should trust.

    from ml.simulation import for_game, DeckList, Game

    sim = for_game(Game.POKEMON)
    result = sim.batch(deck_a, deck_b, games=40, seed=7)
    result.win_rate_a, result.status, result.coverage

Reality check per game (see `.agents/reports/2026-10-28-simulation-engines-research.md`):

* pokemon — `cabt`, measured at 36-47 games/s here; needs integer card ids.
* magic — Forge batch CLI; not installed here, parsing unverified.
* yugioh — no deck-agnostic path; `ygopro-core` is AGPL-3 with a network clause,
  so this package deliberately ships no Yu-Gi-Oh simulator yet.
"""

from __future__ import annotations

from .cabt_adapter import CabtSimulator
from .contract import (
    BatchResult,
    Capabilities,
    DeckList,
    Game,
    GameOutcome,
    Refusal,
    SimStatus,
    Simulator,
)
from .forge_adapter import ForgeSimulator
from .ygopro_adapter import YgoProSimulator


_ADAPTERS: dict[Game, type] = {
    Game.POKEMON: CabtSimulator,
    Game.MAGIC: ForgeSimulator,
    Game.YUGIOH: YgoProSimulator,
}


def for_game(game: Game | str) -> Simulator:
    """Resolve the adapter for a game. Always returns one; it may refuse later."""
    key = Game(game) if not isinstance(game, Game) else game
    return _ADAPTERS[key]()


def capabilities() -> list[Capabilities]:
    return [cls().capabilities() for cls in _ADAPTERS.values()]


__all__ = [
    "BatchResult",
    "Capabilities",
    "DeckList",
    "Game",
    "GameOutcome",
    "Refusal",
    "SimStatus",
    "Simulator",
    "capabilities",
    "for_game",
]
