"""Pokémon adapter over `cabt`, the engine shipped for the Kaggle battle challenge.

This is the one engine measured running full games headless on this laptop:
36-47 games/second with a trivial policy (see
`.agents/reports/2026-10-28-simulation-engines-research.md` §4.2).

Two limits are structural, not implementation gaps:

* Decks are 60 integer card ids, so a deck expressed as card names needs an
  explicit `card_ids` mapping. Without it the adapter refuses rather than
  guessing — a wrong mapping plays a different deck.
* Only one card pool is covered (the challenge format). `coverage` says so.
"""

from __future__ import annotations

from .contract import (
    BatchResult,
    Capabilities,
    DeckList,
    Game,
    GameOutcome,
    Refusal,
    SimStatus,
    Timer,
)


def _engine():
    """Import the engine lazily; absence is a refusal, not an exception."""
    try:
        from kaggle_environments.envs.cabt import cabt as cabt_module
        from kaggle_environments.envs.cabt.cg import game as game_module
    except Exception as exc:  # pragma: no cover - depends on the host
        return None, None, f"kaggle-environments not importable: {exc}"
    return game_module, cabt_module, ""


class CabtSimulator:
    game = Game.POKEMON
    engine = "cabt (kaggle-environments)"

    def capabilities(self) -> Capabilities:
        game_module, _module, why = _engine()
        return Capabilities(
            game=self.game,
            engine=self.engine,
            available=game_module is not None,
            licensed_for_service=False,  # asset terms are uncleared; see the report
            addressable_by="card_id",
            notes=(
                why or "engine importable",
                "one card pool (challenge format)",
                "needs an explicit name->id mapping in DeckList.card_ids",
                "measured 36-47 games/s with a first-option policy",
            ),
        )

    def _deck_ids(self, deck: DeckList) -> list[int]:
        if not deck.card_ids:
            raise Refusal(
                self.game,
                "deck has no card_id mapping",
                "cabt addresses cards by integer id; pass DeckList.card_ids",
            )
        missing = [name for name in deck.cards if name not in deck.card_ids]
        if missing:
            raise Refusal(self.game, f"no id for {len(missing)} cards", f"first: {missing[0]}")
        ids: list[int] = []
        for name, count in deck.cards.items():
            ids.extend([deck.card_ids[name]] * count)
        if len(ids) != 60:
            raise Refusal(self.game, f"deck has {len(ids)} cards, format needs 60")
        return ids

    def batch(self, deck_a: DeckList, deck_b: DeckList, games: int, seed: int = 0) -> BatchResult:
        game_module, _module, why = _engine()
        if game_module is None:
            raise Refusal(self.game, "engine unavailable", why)
        ids_a, ids_b = self._deck_ids(deck_a), self._deck_ids(deck_b)

        timer = Timer()
        outcomes: list[GameOutcome] = []
        errors: list[str] = []
        for _ in range(games):
            try:
                obs, _info = game_module.battle_start(ids_a, ids_b)
                steps = 0
                while obs["current"]["result"] == -1 and steps < 5000:
                    select = obs["select"]
                    obs = game_module.battle_select(list(range(select["maxCount"])))
                    steps += 1
                result = obs["current"]["result"]
                game_module.battle_finish()
                winner = "draw" if result == 0 else ("a" if result == 1 else "b")
                outcomes.append(GameOutcome(winner=winner, turns=steps))
            except Exception as exc:  # pragma: no cover - engine internals
                errors.append(str(exc)[:120])
                try:
                    game_module.battle_finish()
                except Exception:
                    pass
                break

        wins_a = sum(1 for o in outcomes if o.winner == "a")
        wins_b = sum(1 for o in outcomes if o.winner == "b")
        draws = sum(1 for o in outcomes if o.winner == "draw")
        played = len(outcomes)
        notes = ["first-option policy; not a skilled opponent"]
        # A deterministic policy in a mirror match is a broken instrument, not a
        # result: seat order decides every game. Say so instead of reporting 100%.
        mirror = deck_a.cards == deck_b.cards
        degenerate = mirror and played > 1 and (wins_a in (0,) or wins_b in (0,))
        if degenerate:
            notes.append(
                "degenerate: deterministic policy in a mirror match, seat order decides every game"
            )
        if errors:
            notes.append(f"stopped after {len(errors)} engine error(s): {errors[0]}")
        if played < games:
            notes.append(f"asked for {games} games, completed {played}")
        return BatchResult(
            game=self.game,
            deck_a=deck_a,
            deck_b=deck_b,
            games=played,
            wins_a=wins_a,
            wins_b=wins_b,
            draws=draws,
            outcomes=outcomes,
            status=SimStatus.PARTIAL if (errors or played < games or degenerate) else SimStatus.OK,
            engine=self.engine,
            seed=seed,
            wall_ms=timer.ms(),
            notes=notes,
            coverage={"card_pool": "challenge format only", "policy": "first-option"},
        )
