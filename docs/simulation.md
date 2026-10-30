# Simulation: three games, three engines, one contract

There is no shared rules engine for these games, so DeckSage cannot have "a
simulator". It has adapters behind one type system in `src/ml/simulation/`:
`DeckList`, `BatchResult`, `Capabilities`, `Refusal`, and a `Simulator`
protocol. A caller asks `for_game(...)` and gets the same result shape whatever
the engine underneath.

## State of each adapter (2026-10-29)

| Game | Engine | Runnable here | Measured | What blocks it |
|---|---|---|---|---|
| Pokémon | `cabt` (kaggle-environments) | yes, with `--no-deps` install | 114 games/s over 8 games, and 120 games/s over 20 raw | decks must be 60 integer card ids; one card pool |
| Magic | Forge batch CLI (GPL-3) | no jar installed | — | needs `DECKSAGE_FORGE_JAR` + `java`; stdout parse unverified |
| Yu-Gi-Oh! | none | no | — | `ygopro-core` is AGPL-3 with a network clause: a licence decision, not a build task |

Every adapter reports `available=False` with a reason rather than returning a
zero. `for_game("yugioh").batch(...)` raises `Refusal` carrying the licence
reason and the hint.

## Running the Pokémon engine

`kaggle-environments` pulls heavy optional wheels (`pygame`, `tensorstore`) that
do not build on this machine. The cabt engine itself needs only `jsonschema`
and `requests`:

```sh
python -m venv data-local/simenv
data-local/simenv/bin/pip install --no-deps kaggle-environments jsonschema requests
PYTHONPATH=src data-local/simenv/bin/python - <<'PY'
from kaggle_environments.envs.cabt import cabt as C
from ml.simulation import for_game, DeckList, Game
ids = list(C.deck)
cards, mapping = {}, {}
for i in ids:
    cards[f"id_{i}"] = cards.get(f"id_{i}", 0) + 1
    mapping[f"id_{i}"] = i
deck = DeckList(Game.POKEMON, cards, name="sample", card_ids=mapping)
print(for_game("pokemon").batch(deck, deck, games=8).as_dict())
PY
```

## The first honest finding

A mirror match under the engine's first-option policy returns 100% for seat A.
That is the policy, not the deck. The adapter now detects this and reports
`status="partial"` with a note, because a deterministic instrument that always
picks option zero cannot rank two identical decks.

## Contract rules

- A batch result carries `status` and `coverage`. `partial` means the numbers
  exist but some step is unverified; nothing may rank decks on a partial result
  without saying so.
- `DeckList.card_ids` is required whenever the engine addresses cards by id.
  Guessing a mapping would silently play a different deck.
- Measured throughput belongs in the result (`games_per_second`), not in a doc
  that drifts.

## What this cannot establish

A win rate from these engines is a ranking under a named policy, seed panel and
coverage list. It is not a human win rate, not a metagame prediction, and not
evidence that one deck is better in a tournament. `docs/adr/0004-*` sets the
gate any optimisation claim must pass first.
