# DeckSage

Card similarity via tournament deck co-occurrence. Cards that co-occur frequently in tournament decks serve similar functional roles.

**License**: MIT

---

## Installation

**Prerequisites**: Python 3.11+, [uv](https://github.com/astral-sh/uv), [just](https://github.com/casey/just)

```bash
git clone <repo-url>
cd decksage
uv sync
just pre-commit-install
```

---

## Current State

| Game | Cards | Decks |
|------|-------|-------|
| MTG | 35,400 | 55,293 |
| Pokemon | 3,000 | 1,208 |
| Yu-Gi-Oh | 13,930 | 1,500 |

**Performance**: P@10 = 0.088 (baseline) → 0.15-0.20 target (hybrid, in development)

---

## Hybrid Embedding System

5 signals: GNN (30%), Instruction-Tuned (25%), Co-occurrence (20%), Jaccard (15%), Functional Tags (10%)

Formula: `0.30*GNN + 0.25*Instruction + 0.20*Co-occurrence + 0.15*Jaccard + 0.10*Tags`

---

## Quick Start

### 1. Start API

```bash
./scripts/start_api.sh
```

If embeddings don't exist, download from S3 or train (see Development).

### 2. Find Similar Cards

**CLI**:
```bash
decksage similar "Lightning Bolt" --k 5
```

**API**:
```bash
curl "http://localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=fusion&k=5"
```

**Response**:
```json
{
  "query": "Lightning Bolt",
  "results": [
    {"card": "Chain Lightning", "similarity": 0.87},
    {"card": "Shock", "similarity": 0.82}
  ]
}
```

### 3. API Docs

http://localhost:8000/docs (Swagger UI)

---

## API Reference

Base: `http://localhost:8000/v1`

**Endpoints**:
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /cards/{name}/similar` - Find similar cards (params: `mode`, `k`)
- `POST /similar` - Find similar cards (full options)
- `GET /cards/{card}/contextual` - Contextual suggestions (params: `game`, `format`, `archetype`, `top_k`)
- `GET /search` - Search cards (params: `q`, `limit`, `offset`)
- `GET /cards` - List cards (params: `prefix`, `limit`, `offset`)
- `POST /deck/complete` - Complete deck
- `POST /deck/apply_patch` - Apply deck modifications
- `POST /deck/suggest_actions` - Suggest modifications
- `POST /feedback` - Submit feedback

**Error format**: `{"detail": "message"}`  
**Status codes**: 200, 400, 404, 429, 503

See http://localhost:8000/docs for complete schemas.

---

## Data Setup

`data/processed/decks_all_final.jsonl` doesn't exist by default.

**Download from S3**:
```bash
aws s3 sync s3://games-collections/embeddings/ data/embeddings/
```

**Generate from raw data**:
```bash
just extract-mtg
uv run --script scripts/data_processing/unified_export_pipeline.py
```

See `data/README.md` for details.

---

## Architecture

1. Scrape decks → `data/processed/decks_all_final.jsonl`
2. Build graph → `data/graphs/incremental_graph.json`
3. Train embeddings: Node2Vec (PecanPy), E5-base-v2 (zero-shot), GraphSAGE
4. Fusion → Weighted combination
5. API → FastAPI server

**Key files**: `src/ml/api/api.py`, `src/ml/similarity/fusion.py`, `data/graphs/incremental_graph.json`

---

## Development

**Tests**: `just test` | `just test-quick`

**Training**:
```bash
just train-hybrid-full-local        # Local (CPU, slow)
just train-hybrid-full-aws <id>     # AWS (GPU, requires instance ID)
```

**Enrichment**: `just enrich-mtg` | `just enrich-pokemon` | `just enrich-yugioh`

**Note**: Training requires `decks_all_final.jsonl` and `incremental_graph.json`. GNN requires GPU.

---

## Evaluation

**Metrics**: P@K, MRR, NDCG  
**Test sets**: MTG (38/940 queries), Pokemon (10), Yu-Gi-Oh (13)  
**Methodology**: Temporal splits (train <2024, test 2024+), ≥80% vocabulary coverage

```bash
uv run --script scripts/diagnostics/fix_evaluation_coverage.py  # Check coverage
just eval-hybrid-local                                            # Run evaluation
```

Results: `experiments/evaluation_results/`

---

## Troubleshooting

**API won't start**: Check embeddings exist (`ls data/embeddings/*.wv`), port free (`lsof -i :8000`)

**Card not found**: API returns suggestions. Card must be in vocabulary. Check spelling (case-sensitive).

**No similar results**: Card may be too new. Try `--mode fusion`. Check: `curl localhost:8000/ready`

---

## Data Lineage

**Orders**: 0 (raw) → 1 (decks) → 2 (pairs) → 3 (graph) → 4 (embeddings) → 5 (test sets) → 6 (annotations)

Each order depends only on previous. All derived data can be regenerated.

**File sizes**: `decks_all_final.jsonl` (~241 MB), `pairs_large.csv` (~265 MB), `incremental_graph.json` (~3 MB), `magic_128d_pecanpy.wv` (~1 MB)

---

## Known Limitations

- Co-occurrence plateaus at P@10 = 0.08 (hybrid targets 0.15-0.20, not achieved)
- Pokemon: Limited to 3,000 cards (API pagination)
- YGO: Using IDs (Card_12345) - needs mapping
- New cards: Require retraining (instruction-tuned handles zero-shot)

---

## Documentation

- `docs/QUICK_REFERENCE.md` - Daily workflow
- `docs/PRIORITY_MATRIX.md` - Priorities
- `data/README.md` - Data structure

## Contributing

Read `docs/QUICK_REFERENCE.md`, run `just test`, use `just lint`/`just format`. Pre-commit hooks run automatically.

---

## License

MIT - see [LICENSE](LICENSE)
