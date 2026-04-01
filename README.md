# DeckSage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)

Card similarity, search, and deck operations for **Magic: The Gathering**, **Pokemon TCG**, and **Yu-Gi-Oh!**.

DeckSage combines tournament co-occurrence embeddings (PecanPy + Word2Vec on 184K deck lists), card attribute fusion, text search (MeiliSearch + Qdrant), visual embeddings (SigLIP2), and Jaccard co-occurrence to find similar cards, complete partial decks, and surface synergies / substitutes / upgrades.

## Install

Requires Python 3.11+, Docker (for MeiliSearch + Qdrant). Recommended: [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra embeddings
```

For development (adds ruff, pytest, playwright):

```bash
uv sync --extra dev --extra embeddings
```

## Data Assets

Embedding files, graph databases, and processed CSVs are **not stored in git** (too large). To set up a new machine:

1. Obtain the data archive (tarball, ~2 GB compressed / ~6 GB uncompressed)
2. Extract into the repo root: `tar xzf decksage-demo-data.tar.gz`
3. This creates the required files under `data/embeddings/`, `data/graphs/`, `data/processed/`, and `data/cache/`

Required assets (referenced in `.env.example`):
- `data/embeddings/magic_v7_spectral_mu35.wv` (14 MB)
- `data/embeddings/pokemon_v7_fused.wv` (2.3 MB)
- `data/embeddings/yugioh_v7_spectral_mu3.wv` (7.4 MB)
- `data/graphs/{magic,pokemon,yugioh}_unified.db` (5.3 GB total -- card metadata, co-occurrence)
- `data/processed/pairs_*.csv` (456 MB -- Jaccard signal)
- `data/processed/card_attributes_*_enriched.csv` (46 MB)
- `data/cache/text_embeddings/` (205 MB -- optional, rebuilds on startup)

## Usage

### Start the API

```bash
# 1. Start search backends (MeiliSearch + Qdrant)
docker compose up -d meilisearch qdrant

# 2. Copy and edit .env (defaults in .env.example work if data assets are in place)
cp .env.example .env

# 3. Start the API (loads all 3 games, ~40s startup)
uv run uvicorn src.ml.api.api:app --host 127.0.0.1 --port 8001
```

Open `http://localhost:8001` for the web UI, or `http://localhost:8001/docs` for interactive API docs.

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

## Training Data

184K tournament deck lists (Magic 83K, Yu-Gi-Oh 77K, Pokemon 24K) from MTGGoldfish, MTGTop8, Limitless TCG, MasterDuelMeta, YGOProDeck, Archidekt. Six similarity signals: co-occurrence embeddings (PecanPy + Word2Vec, 128D), text embeddings (E5-base-v2), visual embeddings (SigLIP2), Jaccard co-occurrence, functional tag matching, and archetype similarity. See `scripts/training/` for the full pipeline and `docs/experimental_narrative.md` for a walkthrough of 63 experiments.

## Evaluation

~100K LLM-generated annotations across 3 games (~$25 total via Groq 70B + Cerebras 235B cascade). See `data/experiments/SUMMARY.md` for all 63 experiments.

**Co-occurrence embeddings** (v7, substitute nDCG@10, saturated):

| Game | nDCG | Condensed | Gap |
|---|---|---|---|
| Magic | 0.525 | 0.527 | 0.002 |
| Pokemon | 0.437 | 0.438 | 0.001 |
| Yu-Gi-Oh | 0.478 | 0.482 | 0.004 |

**Text embeddings** (E5-base-v2, condensed substitute nDCG@10, 14-25% better):

| Game | Condensed nDCG | vs Co-occurrence |
|---|---|---|
| Magic | 0.613 | +22% |
| Pokemon | 0.518 | +25% |
| Yu-Gi-Oh | 0.532 | +14% |

Eval scripts in `scripts/evaluation/`: `eval_per_mode.py`, `eval_search_relevance.py`, `eval_deck_completion.py`, `intrinsic_eval.py`.

## Project Layout

```
src/ml/           Python ML code (similarity, deck building, search, API, CLI)
src/ml/tests/     Test suite (818 tests)
src/backend/      Go backend (data extraction for 6 games)
frontend/         Web frontend (unified light theme)
scripts/          Training, annotation, evaluation, data processing
tests/e2e/        Playwright E2E tests (45 tests)
data/             Embeddings, pairs, enriched CSVs, annotations, test sets
```

## Development

```bash
just test              # full Python test suite (818 tests)
just lint              # ruff check + format
npx playwright test    # E2E tests (45 tests, requires running server + search backends)
```

Search backends via Docker:

```bash
just qa-deps-up        # start MeiliSearch + Qdrant
just qa-deps-down      # stop
```

## Docs

- `docs/experimental_narrative.md` -- walkthrough of 63 experiments (12 phases), intended for ML audiences
- `data/experiments/SUMMARY.md` -- experiment index with metrics
- `docs/failure_taxonomy.md` -- categorized failure modes from manual analysis
- `docs/figures/experiment_progression.png` -- nDCG progression across experiments

## License

MIT; see [LICENSE](LICENSE).
