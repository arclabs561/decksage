# Agentic interfaces for DeckSage

Status: design note, 2026-10-31. The evidence base is 0076-0082: text retrieves
functional candidates, tags re-order the top-10, and the graph is a co-play
signal, not a substitute signal. An agent should use each for what it measures.

## Tools the API already exposes

| Tool | Endpoint | What it is for | Fields an agent must read |
|---|---|---|---|
| `search` | `POST /v1/search` | free-text/effect search over Meili + E5 + graph | `exact_match`, `results[].score`, `source` |
| `similar` | `POST /v1/similar` | card-name neighbours; `mode=text` for function, `mode=embedding` for co-play | `exact_match`, `model_info.method_used`, `no_vector` |
| `autocomplete` | `GET /v1/cards` | prefix/typo completion over the full catalog | `items[].name`, `total` |
| `contextual` | `GET /v1/cards/{card}/contextual` | curated synergy / alternatives / upgrades / downgrades | per-section `score`, `reasoning` |
| `graph_neighbors` | `GET /v1/graph/neighbors` | weighted deck co-occurrence edges | `neighbors[].weight` (count, not a probability) |
| `deck_complete` | `POST /v1/deck/complete` | fill a partial deck | `steps`, `metrics`, partitions |
| `index_status` | `GET /v1/index/status` | catalog / Meili / Qdrant coverage | `*_coverage` |

`scripts/agentic/card_brief.py` is the smallest composition: one card in, four
evidence sections out (functional candidates, co-play neighbours, graph edges,
contextual sections).

## Agent patterns, in increasing autonomy

1. **Deterministic brief (shipped).** Compose tools and return JSON. No model in
   the loop, no hallucination surface. Use for UI panels and for an agent's
   first tool call.
2. **Tool-using LLM with a fixed playbook.** The model chooses tools to answer
   "what should I cut for a third copy of X?" or "find a budget replacement for
   Y". Bound to 6-8 steps, require a citation (endpoint + card name) per claim,
   and refuse when `index_status` shows low coverage.
3. **Deck-building loop.** Seed deck -> `deck_complete` -> for each added card
   fetch `mode=text` alternatives and `graph_neighbors` -> let the model choose
   cuts/adds with a stated role. Evaluate against the deck-completion gold set,
   not against model prose.

Do not start with (2) or (3) before (1) is measured: the tool contracts are the
cheap, verifiable layer.

## Guardrails learned from the experiments

- **Do not present co-occurrence as substitution.** `mode=embedding` neighbours
  are co-play partners (Skullcrack is a good *substitute*, Llanowar Elves is a
  *co-play* card). The tool name and `method_used` must be shown to the model.
- **`exact_match` is not "has neighbours".** A card can be exact with
  `no_vector: true`; the agent must say "no vector" rather than "not a card".
- **Scores are not comparable across methods.** Text cosine, graph cosine,
  Meili ranking score and tag Jaccard live on different scales. Report the
  method with every number.
- **Labels are model labels.** The pair corpus carries ~0.19 MAE against fresh
  judges and an inflated high band. An agent may cite a label; it may not
  present it as human truth.
- **Graph weights are counts.** Do not normalize them into "probability" or
  compare across games without a shared basis.
- **Legality/banlist claims need the banlist tool.** `state.banlist` exists in
  the API but there is no endpoint yet; do not let prose invent it.

## Evaluation plan

- **Tool level:** response shape, `exact_match`, `no_vector`, coverage; already
  covered by `tests/e2e/api-health.spec.mjs`.
- **Brief level:** for 20 cards, does the brief contain the judged functional
  candidates and the correct co-play neighbours? Precision/recall against the
  refined pair labels.
- **Task level:** 20 partial decks; does the agent's completion beat greedy
  `deck_complete` on the completion gold set? Measure cards added, legality,
  and judged role fit.
- **Honesty:** every claim must map to a tool result; score "uncited claims"
  separately. A fluent answer with no citations fails.

## Interface choice

One consumer (this repo) and an existing HTTP API: a thin Python tool wrapper
over HTTP is enough. Do not add an MCP server until an external client needs
per-user authorization or runtime discovery. The `decksage` CLI already covers
health/similar/search/list; extend it before adding a new protocol surface.

## Next implementation steps

1. `card_brief.py` -> add a `--json`/`--human` switch and a `--budget` flag.
2. Done: `GET /v1/cards/{card}` and `GET /v1/cards/{card}/legality` close the
   two tool gaps an agent hits immediately.
3. A bounded LLM loop (`--agent`) behind a feature flag, with the playbook and
   citation requirement above.
4. Evaluate the brief and the loop on the 20-card/20-deck sets before exposing
   either to the UI.
