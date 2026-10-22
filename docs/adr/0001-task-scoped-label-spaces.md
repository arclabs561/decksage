# ADR-0001: labels are scoped to one task

**Status**: proposed
**Date**: 2026-10-22

## Context

The annotation files carry four score fields per pair: `similarity_score`,
`functional_score`, `synergy_score`, `meta_relevance`, plus an optional
`substitutability`. The same file is then used to evaluate at least five
different products: substitute lookup, synergy lookup, meta pairing, deck
completion, and contextual recall. `eval_per_mode.py` maps mode to field, so one
pair's functional score stands in for "is this a good replacement" while its
synergy score stands in for "does this belong in the same deck".

That mapping breaks in two visible ways. The cascade annotator never writes
`substitutability` or `upgrade_direction`, yet the evaluator reports both, so
those metrics are structurally empty. And agreement is task-dependent:
Krippendorff alpha is 0.62 overall but 0.21 for synergy and 0.40 for
substitutability, meaning the labels that the ranking actually consumes are the
least reliable ones.

## Decision

- Each annotation belongs to exactly one task, recorded as `task` on the pair
  (`substitute`, `synergy`, `meta`, `completion`, `search`).
- A task's evaluator reads only labels for that task. There is no fallback from
  one field to another, and no composite similarity score.
- Judges are asked the task's question directly, not a generic "how similar",
  because the question determines what agreement means.
- Metrics with no labels are reported as absent, never as zero or as a warning
  buried in output.
- Adding a task means adding a label space and a judge prompt, not reusing an
  existing field.

## Rejected

- A single composite similarity score. It hides which question a model is good
  at and makes the per-field agreement differences unactionable.
- Mapping modes onto fields at evaluation time. It silently imports a task the
  annotator never answered.
- Re-labeling everything with one prompt. The failure taxonomy already shows the
  mode matters: co-occurrence partners are complements, not substitutes.

## Consequences

- Historical labels stay usable for the task they were collected for, and must
  be marked instead of reinterpreted.
- Cross-task comparisons stop being possible, which is the point: they were not
  measuring the same thing.
- Each new task costs its own annotation budget and its own calibration against
  human judgments.
- `eval_per_mode.py` loses its field-mapping convenience and gains an explicit
  task argument.
