# DeckSage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)

Card similarity, search, and deck operations for **Magic: The Gathering**, **Pokemon TCG**, and **Yu-Gi-Oh!**.

DeckSage combines tournament co-occurrence embeddings (PecanPy + Word2Vec on 184K deck lists), card attribute fusion, text search (MeiliSearch), and Jaccard co-occurrence to find similar cards, complete partial decks, and surface synergies / substitutes / upgrades.

## Install

Requires Python 3.11+. Recommended: [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra embeddings
```

For development (adds ruff, pytest, playwright):

```bash
uv sync --extra dev --extra embeddings
```

## Usage

### Start the API

DeckSage requires pre-built embedding files (`.wv`). See `scripts/training/` for the training pipeline, or use the pre-built v7 files referenced in `.env`.

```bash
# Copy and edit .env (set embedding paths, API keys)
cp .env.example .env

# Start (loads all 3 games, ~40s startup)
uv run uvicorn src.ml.api.api:app --host 127.0.0.1 --port 8001
```

### CLI

```bash
DECKSAGE="uv run src/ml/cli/main.py"
$DECKSAGE --game magic similar "Lightning Bolt" --k 5 --output table
$DECKSAGE --game magic search "destroy all creatures" --limit 5
$DECKSAGE --game pokemon similar "Ultra Ball" --k 5
$DECKSAGE health --output json
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/live`, `/ready` | GET | Liveness / readiness probes |
| `/v1/games` | GET | List loaded games and card counts |
| `/v1/health?game=magic` | GET | Per-game health (card count, embedding dim) |
| `/v1/similar` | POST | Card similarity (all 6 modes, custom weights) |
| `/v1/cards/{name}/similar` | GET | Card similarity (convenience GET) |
| `/v1/cards/{name}/contextual` | GET | Contextual suggestions (synergies, alternatives, upgrades, downgrades) |
| `/v1/cards?prefix=Light` | GET | Card name autocomplete |
| `/v1/search` | GET/POST | Hybrid text + vector search |
| `/v1/deck/complete` | POST | Deck completion (greedy fill to target size) |
| `/v1/deck/suggest_actions` | POST | Deck improvement suggestions |
| `/v1/deck/apply_patch` | POST | Apply add/remove operations to a deck |
| `/v1/feedback` | POST | Submit user feedback |

Interactive docs at `/docs` when the server is running.

### Similarity modes

| Mode | Method | Use case |
|---|---|---|
| `substitute` | Embedding cosine | Functional replacements (same role/effect) |
| `synergy` | Jaccard co-occurrence | Cards that go in the same deck |
| `meta` | Meta fusion | Competitive metagame pairings |
| `fusion` | Weighted late fusion | Blended signal (all methods) |
| `embedding` | Raw embedding cosine | Direct embedding similarity |
| `jaccard` | Jaccard index | Direct co-occurrence overlap |

## Similarity Signals

| Signal | Source | Status |
|---|---|---|
| Co-occurrence embedding | PecanPy + Word2Vec on 184K decks, 128D, spectral propagation + attribute fusion (v7) | Active |
| Text embedding | E5-base-instruct (instruction-tuned) | Active |
| Jaccard co-occurrence | Deck pair overlap from pairs CSVs | Active |
| Visual embedding | SigLIP card image embeddings | Optional |
| Functional tags | Card type, mana cost, keyword matching | Active |

## Data

| Game | Decks | Embedding vocab | Pairs |
|---|---|---|---|
| Magic | 82,739 | 21,151 (v7 spectral) | 7.1M |
| Pokemon | 24,483 | 4,384 (v7 fused) | 179K |
| Yu-Gi-Oh | 77,016 | 13,745 (v7 spectral) | 1.8M |

Sources: MTGGoldfish, MTGTop8, Limitless TCG, MasterDuelMeta, YGOProDeck.

## Evaluation

Per-mode substitute nDCG@10 (v7 embeddings, ~7,025 annotated queries, ~89K annotations, all games saturated):

| Game | Substitute | Condensed | Gap |
|---|---|---|---|
| Magic | 0.525 | 0.527 | 0.002 |
| Pokemon | 0.437 | 0.438 | 0.001 |
| Yu-Gi-Oh | 0.478 | 0.482 | 0.004 |

Eval scripts in `scripts/evaluation/`: `eval_per_mode.py`, `eval_search_relevance.py`, `eval_deck_completion.py`, `intrinsic_eval.py`.

## Project Layout

```
src/ml/           Python ML code (similarity, deck building, search, API, CLI)
src/ml/tests/     Test suite (~850 tests)
src/backend/      Go backend (data extraction for 6 games)
frontend/         Web frontend (3 game themes, VLM-validated 8/10)
scripts/          Training, annotation, evaluation, data processing
tests/e2e/        Playwright E2E tests (45 tests)
data/             Embeddings, pairs, enriched CSVs, annotations, test sets
```

## Development

```bash
just test         # full Python test suite
just lint         # ruff check + format
npx playwright test  # E2E tests (requires running server + MeiliSearch + Qdrant)
```

Search backends (MeiliSearch, Qdrant) via Docker:

```bash
just qa-deps-up   # start MeiliSearch + Qdrant
just qa-deps-down # stop
```

## License

MIT; see [LICENSE](LICENSE).
