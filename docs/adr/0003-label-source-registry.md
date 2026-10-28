# ADR-0003: external label sources are governed by a registry

**Status**: proposed
**Date**: 2026-10-22

## Context

Labels currently come from LLM judges plus local deck co-occurrence. The
research in `docs/LABEL-SOURCES.md` found a wide field of external candidates:
combo databases, functional tags, precon cut lists, maybeboards, tournament
decks, ban events, forum prose. They differ sharply in what they measure, in
whether automated access is permitted, and in whether derived labels may be
redistributed.

Without a recorded policy, the failure is predictable in two directions. A
scraper gets added because the data was convenient, and the terms were never
read. Or a source is rejected once and the reason is forgotten, so it is
re-litigated every few months. Both happened during this project's first year of
annotation work.

## Decision

- A single registry, `config/label_sources.toml`, lists every external source
  with: the labels it may produce, its access path, its terms, a verdict of
  `adopt`, `trial` or `reject`, and a one-line note.
- `src/ml/data/label_sources.py` loads and validates it, and exposes
  `assert_source_allowed(source, label)` as the guard ingestion code must call
  before using a source.
- The loader refuses duplicate ids, unknown verdict or terms values, an
  usable entry whose terms are `prohibited`, and any usable entry that lists no
  labels.
- `trial` sources may be used for evaluation samples; training use requires the
  caller to check the verdict explicitly, which is the same boundary ADR-0002
  sets for augmentation.
- `reject` records why a source is unusable, so the decision is re-read rather
  than re-argued. Rejection is not a claim that the data is worthless, only that
  it cannot be used here.

## Rejected

- Free-form notes in a markdown table only: readable, but nothing enforces it,
  and code cannot consult it.
- A database or a crawler framework: the registry is the policy layer. Storage
  and fetching come later and are separate decisions.

## Consequences

- Adding a source is a reviewable one-file change with its terms attached.
- The registry boundary rejects prohibited sources and prevents a trial source
  from silently becoming training data; its term classifications still require
  verification against the source.
- The registry will lag reality between updates, so its notes carry the date the
  terms were read.
