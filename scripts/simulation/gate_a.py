#!/usr/bin/env python3
"""Gate A: is the simulator an instrument we may measure with?

ADR-0004 says no optimisation claim is allowed until the instrument passes a set
of cheap, falsifiable checks. This runs them for one game:

1. **Determinism.** The same deck pair on the same seed schedule returns an
   identical per-game result vector. A simulator that varies run to run cannot
   support a comparison.
2. **Self-consistency.** Wins + losses + draws equals games played.
3. **Degeneracy detection.** A mirror match under a deterministic policy must be
   reported as degenerate, not as a decisive result.
4. **Refusal honesty.** A game with no runnable engine refuses with a reason
   instead of returning zeroes.

Exit codes: 0 all checks passed for the selected game, 1 a check failed,
2 the engine is not installed here (nothing was proven either way).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.simulation import DeckList, Game, Refusal, SimStatus, for_game


def _sample_deck(game: Game) -> DeckList:
    """A deck the engine itself ships, so the check is not about our card data."""
    if game is Game.POKEMON:
        from kaggle_environments.envs.cabt import cabt as cabt_module

        ids = list(cabt_module.deck)
        cards: dict[str, int] = {}
        mapping: dict[str, int] = {}
        for card_id in ids:
            name = f"id_{card_id}"
            cards[name] = cards.get(name, 0) + 1
            mapping[name] = card_id
        return DeckList(game, cards, name="engine-sample", card_ids=mapping)
    raise Refusal(game, "no sample deck available for this game")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="pokemon", choices=[g.value for g in Game])
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    game = Game(args.game)
    sim = for_game(game)
    caps = sim.capabilities()
    checks: list[dict] = []

    if not caps.available:
        payload = {
            "game": str(game),
            "engine": caps.engine,
            "verdict": "NOT_PROVEN",
            "reason": caps.notes[0] if caps.notes else "engine unavailable",
            "checks": [],
        }
        print(
            json.dumps(payload, indent=2)
            if args.json
            else f"{game}: NOT_PROVEN — {payload['reason']}"
        )
        return 2

    try:
        deck = _sample_deck(game)
    except Refusal as exc:
        print(f"{game}: NOT_PROVEN — {exc}")
        return 2

    first = sim.batch(deck, deck, games=args.games, seed=args.seed)
    second = sim.batch(deck, deck, games=args.games, seed=args.seed)

    vector_a = [(o.winner, o.turns) for o in first.outcomes]
    vector_b = [(o.winner, o.turns) for o in second.outcomes]
    checks.append(
        {
            "name": "determinism",
            "passed": vector_a == vector_b and len(vector_a) == args.games,
            "detail": f"{len(vector_a)} vs {len(vector_b)} games; identical={vector_a == vector_b}",
        }
    )

    total = first.wins_a + first.wins_b + first.draws
    checks.append(
        {
            "name": "self_consistency",
            "passed": total == first.games,
            "detail": f"wins_a={first.wins_a} wins_b={first.wins_b} draws={first.draws} games={first.games}",
        }
    )

    # a deterministic policy in a mirror match cannot rank the same deck twice
    mirror = deck.cards == deck.cards
    degenerate_reported = first.status is SimStatus.PARTIAL and any(
        "degenerate" in note for note in first.notes
    )
    checks.append(
        {
            "name": "degeneracy_reported",
            "passed": (not mirror) or degenerate_reported,
            "detail": f"mirror={mirror} status={first.status} notes={first.notes[:1]}",
        }
    )

    failed = [c for c in checks if not c["passed"]]
    payload = {
        "game": str(game),
        "engine": caps.engine,
        "games_per_second": round(first.games_per_second or 0, 1),
        "verdict": "PASS" if not failed else "FAIL",
        "checks": checks,
        "summary": first.as_dict(),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"{game} via {caps.engine}: {payload['verdict']} ({payload['games_per_second']} games/s)"
        )
        for c in checks:
            print(f"  [{'pass' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
