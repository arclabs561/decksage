# DeckSage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)

Card similarity search and deck operations for **Magic: The Gathering**, **Pokemon TCG**, and **Yu-Gi-Oh!**.

Given a card name, DeckSage returns the most similar cards by combining tournament co-occurrence embeddings (Word2Vec / Node2Vec on deck lists), text embeddings, and Jaccard co-occurrence via late fusion. It also provides deck completion (greedy fill, suggestion, patching) and faceted semantic search.

## Install

Requires Python 3.11+. Recommended: [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra embeddings
```

For development (adds ruff, pytest, hypothesis):

```bash
uv sync --extra dev --extra embeddings
```

## Usage

### Start the API

DeckSage requires pre-built embedding files (`.wv`). Generate them with `just train-runctl-local` or the training scripts in `scripts/training/`.

```bash
# Single game
export DECKSAGE_DEFAULT_GAME=magic
export EMBEDDINGS_PATH=/path/to/magic.wv
uv run uvicorn ml.api.api:app --reload --port 8000
```

```bash
# Multiple games in one process
export DECKSAGE_GAMES=magic,pokemon,yugioh
export DECKSAGE_DEFAULT_GAME=magic
export EMBEDDINGS_PATH_MAGIC=/path/to/magic.wv
export EMBEDDINGS_PATH_POKEMON=/path/to/pokemon.wv
export EMBEDDINGS_PATH_YUGIOH=/path/to/yugioh.wv
uv run uvicorn ml.api.api:app --reload --port 8000
```

In multi-game mode, requests must include the `game` parameter (query param or JSON body).

### CLI

```bash
decksage --url http://localhost:8000 --game magic similar "Lightning Bolt" --k 5
decksage --url http://localhost:8000 --game magic search "lightning" --output json
decksage --url http://localhost:8000 --game magic ready
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ready`, `/live` | GET | Readiness / liveness probes |
| `/v1/games` | GET | List loaded games |
| `/v1/health?game=magic` | GET | Per-game health (card count, embedding dim) |
| `/v1/similar` | POST | Card similarity search (returns ranked list) |
| `/v1/cards?game=magic&prefix=Light` | GET | Card name lookup / autocomplete |
| `/v1/search` | POST | Faceted semantic search (requires Meilisearch + Qdrant) |
| `/v1/deck/*` | POST | Deck operations: apply patch, complete, suggest |
| `/v1/feedback` | POST | Submit user feedback |

Interactive docs at `/docs` when the server is running.

## Similarity Signals

DeckSage fuses multiple similarity signals per query. Each signal is optional; the system uses whichever artifacts are available.

| Signal | Source | Method | Status |
|---|---|---|---|
| Co-occurrence embedding | Tournament deck lists | Word2Vec / Node2Vec (cosine) | Active |
| Text embedding | Card text | Sentence transformers (cosine) | Active |
| Jaccard co-occurrence | Deck pair overlap | Jaccard index | Active |
| Visual embedding | Card images | SigLIP / CLIP (cosine) | Requires external artifacts |
| GNN embedding | Co-occurrence graph | GraphSAGE (cosine) | Requires external artifacts |
| Functional tags | Card attributes | Jaccard similarity | Not loaded |

Aggregation methods: reciprocal rank fusion (default), inverse square root, weighted linear, CombSUM, CombMNZ, CombMAX, CombMIN. MMR diversification is available.

## Project Layout

```
src/ml/           Python ML code (similarity, deck building, search, training, API, CLI)
src/ml/tests/     Test suite (698 tests)
src/backend/      Go backend (scraper, data extraction, transforms)
frontend/         Web frontend
scripts/          Data pipeline and training scripts
tests/e2e/        End-to-end Playwright tests
```

## Development

```bash
just test-quick   # fast subset
just test         # full suite
just lint         # ruff check
just format       # ruff format
```

Optional search backends (Meilisearch, Qdrant) via Docker:

```bash
docker compose up -d
```

## License

MIT; see [LICENSE](LICENSE).
