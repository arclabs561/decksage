# DeckSage

Card similarity and deck operations for trading card games.

- **Games**: `magic`, `pokemon`, `yugioh`
- **Interfaces**: HTTP API (`/docs`), CLI (`decksage`)

## Upstream vs this branch

This workspace often tracks `origin/main` as the upstream baseline. This README describes behavior on this branch.

| Area | Upstream (`origin/main`) | This branch |
| --- | --- | --- |
| Multi-game serving | Mostly single-game, global state. | Per-game `ApiState`; `/v1/games`; `game` required when `DECKSAGE_GAMES` lists multiple games. |
| Validation | Import-time stubs and legality gaps existed. | Deterministic deck models; optional banlist legality checking. |
| Search | Could fall back to substring matching when backends were missing. | `/v1/search` is fail-closed; indices/collections are namespaced per game. |
| Data paths | Some defaults assumed MTG-specific layouts. | Canonical default paths for card data + artifacts. |

For details, see `git log origin/main..HEAD`.

## Install

Requirements: Python 3.11+. Recommended: [uv](https://github.com/astral-sh/uv). Optional: [just](https://github.com/casey/just).

```bash
uv sync
```

For development:

```bash
uv sync --extra dev
```

## Run the API

### Single-game (default)

Configure artifacts:

```bash
export DECKSAGE_DEFAULT_GAME=magic
export EMBEDDINGS_PATH=/path/to/magic.wv
export PAIRS_PATH=/path/to/magic_pairs.csv          # optional (enables jaccard/fusion)
export ATTRIBUTES_PATH=/path/to/magic_attrs.csv      # optional (enables faceted + richer fusion)
```

Start:

```bash
uv run uvicorn ml.api.api:app --reload --port 8000
curl http://localhost:8000/ready
```

### Multi-game (one process)

Configure games + per-game artifacts:

```bash
export DECKSAGE_GAMES=magic,pokemon,yugioh
export DECKSAGE_DEFAULT_GAME=magic

export EMBEDDINGS_PATH_MAGIC=/path/to/magic.wv
export PAIRS_PATH_MAGIC=/path/to/magic_pairs.csv

export EMBEDDINGS_PATH_POKEMON=/path/to/pokemon.wv
export PAIRS_PATH_POKEMON=/path/to/pokemon_pairs.csv

export EMBEDDINGS_PATH_YUGIOH=/path/to/yugioh.wv
export PAIRS_PATH_YUGIOH=/path/to/yugioh_pairs.csv
```

Optional per-game knobs:

```bash
export SIGNALS_DIR_MAGIC=/path/to/signals/magic
export FUSION_WEIGHTS_PATH_MAGIC=/path/to/fusion_weights_magic.json
export RERANKER_PATH_MAGIC=/path/to/reranker_magic.pkl

export MEILISEARCH_INDEX_MAGIC=cards_magic
export QDRANT_COLLECTION_MAGIC=cards_magic
```

Start + check:

```bash
uv run uvicorn ml.api.api:app --reload --port 8000
curl http://localhost:8000/v1/games
curl "http://localhost:8000/v1/health?game=magic"
```

In multi-game mode, requests must specify `game` (query param or JSON field).

## CLI

The CLI targets a specific game via `--game`:

```bash
decksage --url http://localhost:8000 --game magic ready
decksage --url http://localhost:8000 --game magic similar "Lightning Bolt" --k 5
decksage --url http://localhost:8000 --game magic search "lightning" --output json
```

## API (minimal)

Base: `http://localhost:8000`

- **Readiness**: `GET /ready`, `GET /live`
- **Game inventory**: `GET /v1/games`
- **Health**: `GET /v1/health?game=magic`
- **Similarity**: `POST /v1/similar` (body includes `game` in multi-game mode)
- **Cards**: `GET /v1/cards?game=magic&prefix=Light&limit=10`
- **Search**: `POST /v1/search` (requires Meilisearch and/or Qdrant; Qdrant needs embeddings)
- **Deck ops**: `POST /v1/deck/apply_patch`, `POST /v1/deck/complete`, `POST /v1/deck/suggest_actions`
- **Feedback**: `POST /v1/feedback` (set `game` in multi-game mode)

## Data

Large artifacts are not checked into git. See:

- `data/README.md` (expected layout)
- `scripts/` and `justfile` (build/sync pipelines)

If you have access, some pipelines sync from S3 (see `data/README.md`).

## Development

```bash
just test-quick
just test
just lint
just format
```

See `justfile` for additional targets.

## Docs

- `docs/quick-reference.md`
- `docs/priority-matrix.md`
- `src/ml/search/README.md`

## License

MIT; see `LICENSE`.
