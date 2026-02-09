# Data directory

This repo commits small metadata under `data/`. Most runtime outputs and large artifacts (decks, graphs, embeddings) are ignored and must be generated or synced.

## What is tracked vs ignored

Tracked (in git):

- small metadata (JSON/YAML) used by the system

Ignored / external (not in git):

- local API outputs (e.g. query history, user feedback JSONL)
- large raw exports and processed datasets
- graph edgelists and derived graph artifacts
- embedding models (`*.wv`) and other model outputs

The exact ignore rules live in `.gitignore`.

## Expected layout (conceptual)

```
data/
  analytics/        # local logs (ignored by default)
  annotations/      # tracked examples + local feedback outputs (JSONL ignored)
  game_knowledge/   # small, tracked JSON knowledge per game

  raw/              # ignored (large)
  processed/        # ignored (large)
  decks/            # ignored (large)
  graphs/           # ignored (generated)
  embeddings/       # ignored (generated)
```

## Pipelines

Unified deck export pipeline:

```bash
uv run scripts/data_processing/unified_export_pipeline.py --help
uv run scripts/data_processing/unified_export_pipeline.py
```

Multi-game pairs regeneration:

```bash
uv run scripts/data_processing/regenerate_multi_game_pairs.py --help
uv run scripts/data_processing/regenerate_multi_game_pairs.py
```

## Syncing (optional)

Some workflows sync to/from S3 (project bucket typically looks like `s3://games-collections/...`). See:

- `scripts/data_processing/export_from_s3.sh`
- `scripts/data_processing/sync_to_s3.sh`
- `scripts/data_processing/sync_all_to_s3.sh`
