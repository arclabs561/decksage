# Publishing policy

The repository is private today and may become public later. This file records
what may be shared, what must not, and how to remove what should never have
been committed.

## Shareable

- Source code, tests, scripts, configs, docs (MIT, code only).
- Experiment records in `data/experiments/` (YAML plus `SUMMARY.md`), because
  they describe method and measured results without containing the corpora.
- Small test fixtures that the suite needs to run.
- Explicitly released trained assets: LoRA adapters, cross-encoder heads, and
  exported embedding files, when their own release is recorded and their
  training data is described. These are derived works, not the source data.

## Not shareable

- Raw card data, deck lists, tournament exports, and price scrapes. Their
  upstream terms (Scryfall, pokemontcg.io, YGOPRODeck, Archidekt, MTGGoldfish,
  Limitless) do not grant redistribution.
- Annotation corpora and per-pair judgments under `data/annotations/` and
  `data/test_sets/`. They are expensive to produce, encode model choices, and
  were judged by third-party models whose terms may restrict redistribution.
- Published card art and screenshots. The MIT license cannot cover them.
- Derived embeddings and graph databases built from those corpora. An embedding
  file is a compressed representation of the deck corpus and is treated as
  data, not code, until a release decision says otherwise.

## Procedure

1. Run `scripts/maintenance/purge-history.sh`. It reads
   `scripts/maintenance/purge-paths.txt`, writes a bundle backup, and
   rewrites every ref.
2. Verify with the commands the script prints. Each must return nothing.
3. Force-push with `git push --force-with-lease origin main`.
4. Hosts keep unreachable objects cached until garbage collection. For a
   public repository, recreate it from the rewritten checkout or ask the host
   to purge the objects; a force-push alone is not proof of removal.

## Configuration for other people

A fresh clone needs its own data and configuration, and the README states that
the demo archive is not publicly available. Others can still run the code path
by supplying their own corpora under `data/` and their own `.env` copied from
`.env.example`, whose defaults point at relative paths. `DECKSAGE_DEVICE`
selects the compute device (MPS by default, `cpu` or `cuda` otherwise).
