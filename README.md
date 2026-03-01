# DeckSage

Card similarity and deck operations for trading card games.

- **Games Supported**: `magic`, `pokemon`, `yugioh`
- **Interfaces**: HTTP API (`/docs`), CLI (`decksage`)

## Quick Start

Requirements: Python 3.11+. Recommended: [uv](https://github.com/astral-sh/uv). Optional: [just](https://github.com/casey/just).

### Installation

```bash
uv sync --extra embeddings
```

For development:

```bash
uv sync --extra dev --extra embeddings
```

## Artifacts

The API requires pre-built embedding files (`.wv`) and optional CSV files for card pairs/attributes. Generate them with `just train` or see `docs/quick-reference.md` for details on the data pipeline.

## Running the API (development)

You can run DeckSage in single-game or multi-game mode.

### Single-game Mode (Default)

Configure the necessary artifacts and start the server:

```bash
export DECKSAGE_DEFAULT_GAME=magic
export EMBEDDINGS_PATH=/path/to/magic.wv
# Optional:
export PAIRS_PATH=/path/to/magic_pairs.csv
export ATTRIBUTES_PATH=/path/to/magic_attrs.csv

uv run uvicorn ml.api.api:app --reload --port 8000
```

### Multi-game Mode

Run multiple games in a single process by configuring them explicitly:

```bash
export DECKSAGE_GAMES=magic,pokemon,yugioh
export DECKSAGE_DEFAULT_GAME=magic

# Magic config
export EMBEDDINGS_PATH_MAGIC=/path/to/magic.wv
export PAIRS_PATH_MAGIC=/path/to/magic_pairs.csv

# Pokemon config
export EMBEDDINGS_PATH_POKEMON=/path/to/pokemon.wv

# Yugioh config
export EMBEDDINGS_PATH_YUGIOH=/path/to/yugioh.wv

uv run uvicorn ml.api.api:app --reload --port 8000
```

*Note: In multi-game mode, API requests must specify the `game` (as a query param or in the JSON body).*

## CLI Usage

The DeckSage CLI targets a specific game via `--game`:

```bash
decksage --url http://localhost:8000 --game magic ready
decksage --url http://localhost:8000 --game magic similar "Lightning Bolt" --k 5
decksage --url http://localhost:8000 --game magic search "lightning" --output json
```

## API Overview

Base URL: `http://localhost:8000`

- `GET /ready`, `GET /live`: Readiness and liveness checks
- `GET /v1/games`: List supported games
- `GET /v1/health?game=magic`: Game-specific health check
- `POST /v1/similar`: Card similarity search
- `GET /v1/cards?game=magic&prefix=Light`: Card lookup and auto-complete
- `POST /v1/search`: Faceted semantic search (requires Meilisearch + Qdrant; see `src/ml/search/README.md`)
- `POST /v1/deck/*`: Deck operations (apply patch, complete, suggest actions)
- `POST /v1/feedback`: Submit user feedback

## Development

Use `just` to run development tasks:

```bash
just test-quick
just test
just lint
just format
```

## Docker

A `docker-compose.yml` is provided for running the optional search backends (Meilisearch, Qdrant):

```bash
docker compose up -d
```

## Documentation

For more detailed information, see:
- `docs/quick-reference.md`
- `docs/priority-matrix.md`
- `src/ml/search/README.md`

## License

MIT; see `LICENSE`.
