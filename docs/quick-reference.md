# DeckSage quick reference

Keep this file operational: commands, invariants, and the minimum pointers. Put planning and metrics elsewhere.

## Entry points

- `README.md`: run + configure (single-game + multi-game)
- `data/README.md`: expected data layout + pipelines (large artifacts are not in git)
- `src/ml/search/README.md`: Meilisearch/Qdrant setup + indexing

## Development workflow

Most repo workflows are wrapped in `justfile`.

```bash
just sync
just test-quick
just lint
just format
```

More:

```bash
just test
just test-api
just test-slow
```

## Run the API (fast path)

Single game (default):

```bash
export DECKSAGE_DEFAULT_GAME=magic
export EMBEDDINGS_PATH=/path/to/magic.wv
uv run uvicorn ml.api.api:app --reload --port 8000
curl http://localhost:8000/ready
```

Multi-game (one process):

```bash
export DECKSAGE_GAMES=magic,pokemon,yugioh
export EMBEDDINGS_PATH_MAGIC=/path/to/magic.wv
export EMBEDDINGS_PATH_POKEMON=/path/to/pokemon.wv
export EMBEDDINGS_PATH_YUGIOH=/path/to/yugioh.wv

uv run uvicorn ml.api.api:app --reload --port 8000
curl http://localhost:8000/v1/games
```

In multi-game mode, requests must specify `game` (query param or JSON field).

## CLI

```bash
decksage --url http://localhost:8000 --game magic ready
decksage --url http://localhost:8000 --game magic similar "Lightning Bolt" --k 5
decksage --url http://localhost:8000 --game magic search "lightning" --output json
```

## Operational invariants

- **Readiness is per game**: in multi-game mode, `/ready` returns 503 until all configured games have embeddings loaded.
- **Search is fail-closed**: `/v1/search` requires Meilisearch and/or Qdrant; Qdrant vector search requires embeddings.
- **Large data is out-of-repo**: `data/` contains small metadata + local outputs; big artifacts are ignored/synced/generated.
