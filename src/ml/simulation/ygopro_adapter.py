"""Yu-Gi-Oh! adapter: deliberately absent.

The only real engines are `ygopro-core` (AGPL-3) and its derivatives. AGPL-3 §13
obliges anyone offering the engine *as a network service* to offer the
Corresponding Source to its users, which is a licensing decision for this repo,
not an implementation detail. The bots that exist (WindBot) need per-deck
compiled executors, and the batched environments are Linux-only.

So this adapter exists to say that clearly, in the same shape as the others,
instead of leaving a missing branch for someone to guess about.
"""

from __future__ import annotations

from .contract import (
    BatchResult,
    Capabilities,
    DeckList,
    Game,
    Refusal,
)


REASON = "no deck-agnostic headless Yu-Gi-Oh! engine is licensed for this service"
HINT = "ygopro-core is AGPL-3 (network clause); decide the licence question before building this"


class YgoProSimulator:
    game = Game.YUGIOH
    engine = "none (licence decision pending)"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            game=self.game,
            engine=self.engine,
            available=False,
            licensed_for_service=False,
            addressable_by="card_id",
            notes=(REASON, HINT, "WindBot needs per-deck compiled executors"),
        )

    def batch(self, deck_a: DeckList, deck_b: DeckList, games: int, seed: int = 0) -> BatchResult:
        raise Refusal(self.game, REASON, HINT)
