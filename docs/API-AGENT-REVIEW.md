# API agent review, 2026-10-31

Two reviewers: a deterministic probe suite (`scripts/agentic/api_critique.py`)
and a headless tool-calling agent that only sees the API. The agent's prose
is checked against the live service before it shapes work.

## Claims, checked

| claim | verdict | evidence |
| --- | --- | --- |
| `/v1/similar` returns a different shape per mode | refuted | all modes return ['exact_match', 'feedback_url', 'model_info', 'query', 'query_metadata', 'results'] |
| `graph_neighbors` defaults to co-occurrence only | refuted | default page holds 50 edges across ['cooccurrence', 'tag', 'text'] |
| search ignores offset / cannot paginate | fixed | offset=2 returns a disjoint page after ['Dragon', 'Dragon Fangs']; next_offset advances |
| deck completion only accepts raw text | partly true | `deck`(partitions) and `deck_text` already existed; `cards` now accepted, steps=2 |
| `mode` and `relations` are bare strings | true of the tool schema, not the API | FastAPI request models already expose Literals; the reviewer's tool schema was ours |

Two of the five claims were wrong, which is why the probes decide what gets
fixed. The agent's real signal was naming: it reached for `mtg`, `pkmn`,
`ygo` and lost whole tool calls to 400s it could not recover from.

## Fixed

- Game aliases normalised at the boundary (`mtg`, `mtg arena`, `pkmn`, `ptcg`,
  `ygo`, `yu gi oh`); an unknown game names the valid set in one sentence.
- `/health` alias; agents and orchestrators probe it, not `/live`.
- `/v1/graph/stats` for edge counts, mean and max weight per relation.
- `/v1/graph/neighbors` rejects unknown relations instead of returning `[]`.
- `/v1/search` supports `offset` and `next_offset`; a page slices one ranking.
- `/v1/deck/complete` accepts `cards=[{name, count}]` and `deck_text`.
- Validation errors keep FastAPI's `detail` list and add a one-line `message`.

## Not fixed, on purpose

- The first `mode=text` call costs ~0.6s to load the vector matrix; steady state
  is ~15ms. Moving that to startup slows every health check for one request.
- `mode` and `relations` are already typed in the OpenAPI schema. Only the
  reviewer's tool schema was loose; it now carries enums.

Generated 2026-10-31T20:15:20+00:00.
