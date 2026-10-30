"""One simulation contract, one type system, three very different engines.

Every game needs its own simulator — there is no shared rules engine — so the
only real choice is whether the *shape* of a simulated result is shared. It is:
an adapter converts a `DeckList` pair into whichever form its engine wants and
returns the same `BatchResult` regardless of game.

Two rules keep this honest:

* An adapter that cannot run says so. It raises `Refusal` with the reason
  (missing binary, unlicensed engine, name-to-id mapping unavailable) instead of
  returning a plausible-looking zero.
* A batch result carries its own coverage and status. `status="partial"` means
  the numbers exist but the adapter could not verify part of the pipeline, and
  no consumer may rank decks on a partial result without saying so.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Game(StrEnum):
    MAGIC = "magic"
    POKEMON = "pokemon"
    YUGIOH = "yugioh"


class SimStatus(StrEnum):
    OK = "ok"
    """The whole pipeline ran and the numbers are what they claim."""
    PARTIAL = "partial"
    """Numbers exist, but some step is unverified (say which in `notes`)."""
    REFUSED = "refused"
    """Nothing ran; `notes` gives the reason."""


@dataclass(frozen=True)
class DeckList:
    """A deck in the only form every engine can be given: exact card counts."""

    game: Game
    cards: dict[str, int]
    name: str = ""
    # Some engines address cards by integer id rather than name. When that is
    # required the mapping must be explicit; guessing would silently play a
    # different deck than the one requested.
    card_ids: dict[str, int] | None = None

    @property
    def size(self) -> int:
        return sum(self.cards.values())

    def as_lines(self) -> list[str]:
        return [f"{count} {card}" for card, count in self.cards.items()]


@dataclass(frozen=True)
class GameOutcome:
    winner: str  # "a" | "b" | "draw"
    turns: int | None = None
    reason: str | None = None


@dataclass
class BatchResult:
    """The result shape every adapter returns, for every game."""

    game: Game
    deck_a: DeckList
    deck_b: DeckList
    games: int
    wins_a: int = 0
    wins_b: int = 0
    draws: int = 0
    outcomes: list[GameOutcome] = field(default_factory=list)
    status: SimStatus = SimStatus.OK
    engine: str = ""
    seed: int | None = None
    wall_ms: int = 0
    notes: list[str] = field(default_factory=list)
    coverage: dict[str, str] = field(default_factory=dict)

    @property
    def win_rate_a(self) -> float | None:
        decided = self.wins_a + self.wins_b
        return (self.wins_a / decided) if decided else None

    @property
    def games_per_second(self) -> float | None:
        return (self.games / (self.wall_ms / 1000)) if self.wall_ms else None

    def as_dict(self) -> dict:
        return {
            "game": str(self.game),
            "engine": self.engine,
            "status": str(self.status),
            "seed": self.seed,
            "games": self.games,
            "wins_a": self.wins_a,
            "wins_b": self.wins_b,
            "draws": self.draws,
            "win_rate_a": self.win_rate_a,
            "games_per_second": self.games_per_second,
            "wall_ms": self.wall_ms,
            "coverage": self.coverage,
            "notes": self.notes,
            "deck_a": {"name": self.deck_a.name, "size": self.deck_a.size},
            "deck_b": {"name": self.deck_b.name, "size": self.deck_b.size},
        }


class Refusal(RuntimeError):
    """Raised when an adapter cannot produce an honest result."""

    def __init__(self, game: Game, reason: str, hint: str = "") -> None:
        self.game = game
        self.reason = reason
        self.hint = hint
        super().__init__(f"{game}: {reason}" + (f" ({hint})" if hint else ""))


@dataclass(frozen=True)
class Capabilities:
    """What an adapter can be asked to do, declared before it is asked."""

    game: Game
    engine: str
    available: bool
    licensed_for_service: bool
    addressable_by: str  # "name" | "card_id"
    notes: tuple[str, ...] = ()


@runtime_checkable
class Simulator(Protocol):
    game: Game

    def capabilities(self) -> Capabilities: ...

    def batch(
        self, deck_a: DeckList, deck_b: DeckList, games: int, seed: int = 0
    ) -> BatchResult: ...


class Timer:
    """Wall-clock measurement, kept out of the adapters' logic."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
