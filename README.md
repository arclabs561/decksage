# DeckSage

Card similarity and deck building for Magic: The Gathering, Pokemon TCG, and Yu-Gi-Oh.

Finds substitutes, synergies, and completes partial decks using co-occurrence embeddings (PecanPy on 184K deck lists), text similarity (E5), visual similarity (SigLIP2), Jaccard overlap, functional tags, and archetype matching.

## Setup

Requires Python 3.11+, Docker, [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra embeddings
```

Embedding files, graph databases, and processed CSVs are not in git (~6 GB uncompressed).
The demo archive is currently an unavailable public prerequisite: this repository
does not provide a public download or a verified end-to-end archive build command.
A fresh clone cannot reproduce the demo until these artifacts are supplied.
If you already have a trusted copy, extract it into the repo root:

```bash
tar xzf decksage-demo-data.tar.gz   # creates data/embeddings/, data/graphs/, data/processed/
cp .env.example .env                 # defaults work with extracted paths
```

## Run

```bash
docker compose up -d meilisearch qdrant          # search backends
uv run uvicorn src.ml.api.api:app --port 8001     # ~40s startup, loads all 3 games
```

Open `http://localhost:8001` for the UI, or `/docs` for interactive API docs.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/live`, `/ready` | GET | Health probes |
| `/v1/games` | GET | Loaded games and card counts |
| `/v1/similar` | POST | Card similarity (6 modes, custom weights) |
| `/v1/cards/{name}/similar` | GET | Card similarity (convenience) |
| `/v1/cards/{name}/contextual` | GET | Synergies, alternatives, upgrades, downgrades |
| `/v1/cards?prefix=Light` | GET | Autocomplete |
| `/v1/search` | GET/POST | Hybrid text + vector search |
| `/v1/deck/complete` | POST | Deck completion (greedy, beam, or optimal transport) |
| `/v1/deck/suggest_actions` | POST | Deck improvement suggestions |

### Similarity modes

| Mode | Signal | Use case |
|---|---|---|
| `substitute` | Text similarity (E5) | Functional replacements |
| `synergy` | Jaccard co-occurrence | Cards that belong in the same deck |
| `fusion` | Weighted late fusion (all 6 signals) | Blended ranking |
| `embedding` | Co-occurrence cosine | Direct embedding distance |
| `jaccard` | Jaccard index | Direct co-occurrence overlap |
| `meta` | Meta fusion | Competitive metagame pairings |

## CLI

```bash
DECKSAGE="uv run src/ml/cli/main.py"
$DECKSAGE --game magic similar "Lightning Bolt" --k 5 --output table
$DECKSAGE --game magic search "destroy all creatures" --limit 5
$DECKSAGE --game pokemon similar "Ultra Ball" --k 5
```

## Cloud automation

Cloud operations require your own destinations. Set `BUCKET=s3://your-bucket`
for `scripts/data_processing/sync_to_s3.sh` and `scripts/review_s3_buckets.sh`.
Extraction accepts an explicit `BUCKET` URI and never auto-creates buckets.
The Go dataset CLI requires `--bucket` (or `--bucket-url` for transform/index).
The auto-stop script requires `GNN_OUTPUT` and `EVAL_OUTPUT` as complete S3
object URIs for the run whose instance you want to stop. Daily updates retain
logs locally unless `S3_LOG_DESTINATION` is set; `--dry-run` never uploads logs.
Other cloud shell workflows and S3 model-card/asset publishing use
`DECKSAGE_S3_BUCKET` (a bucket name, without `s3://`). Existing per-script
`S3_DATA`, `S3_OUTPUT` and `S3_BUCKET` overrides still take precedence where
supported. Cloud workflows fail when a required destination is unset.

## Development

```bash
just test     # 834 unit tests
just lint     # ruff check + format
npx playwright test   # 41 E2E tests (requires running server + search backends)
just qa-deps-up       # start MeiliSearch + Qdrant
just qa-deps-down     # stop
```

## Layout

```
src/ml/           Python ML code (similarity, deck building, search, API, CLI)
src/ml/tests/     Test suite
src/backend/      Go backend (data extraction for 6 games)
frontend/         Web UI
scripts/          Training, annotation, evaluation, data processing
tests/e2e/        Playwright E2E tests
data/             Embeddings, graphs, annotations, test sets (not in git)
```

## Evaluation

~100K LLM-generated annotations across 3 games (~$25 total via Groq 70B + Cerebras 235B cascade). Substitute nDCG@10 (condensed, saturated):

| Game | Co-occurrence | Text (E5) | Improvement |
|---|---|---|---|
| Magic | 0.527 | 0.613 | +16% |
| Pokemon | 0.438 | 0.518 | +18% |
| Yu-Gi-Oh | 0.482 | 0.532 | +10% |

See `docs/experimental_narrative.md` for a walkthrough of 63 experiments and `docs/failure_taxonomy.md` for categorized failure modes.

## License

MIT
