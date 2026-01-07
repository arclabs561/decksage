# DeckSage

ML-powered card similarity and recommendations for trading card games. Find budget substitutions, complete decks, and discover similar cards using graph neural networks and tournament deck co-occurrence analysis.

**Status**: Active development | **License**: MIT

---

## Features

- **Multi-modal similarity search**: Combines graph embeddings, instruction-tuned embeddings, visual embeddings, co-occurrence patterns, and functional tags
- **Budget substitutions**: Find cheaper alternatives that serve similar roles
- **Deck completion**: AI-powered suggestions to finish incomplete decks
- **Contextual recommendations**: Format, archetype, and meta-aware suggestions
- **Multi-game support**: Magic: The Gathering, Pokemon, Yu-Gi-Oh

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (package manager)
- [just](https://github.com/casey/just) (command runner)

### Installation

```bash
git clone https://github.com/arclabs561/decksage.git
cd decksage
uv sync
just pre-commit-install
```

### Start the API

```bash
./scripts/start_api.sh
# Or: just serve
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Find Similar Cards

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
    {"card": "Shock", "similarity": 0.82},
    {"card": "Lava Spike", "similarity": 0.79}
  ],
  "model_info": {
    "method_used": "fusion",
    "num_cards": 35400
  }
}
```

---

## Architecture

DeckSage uses a hybrid embedding system combining multiple signals:

1. **Graph Neural Networks (30%)**: Multi-hop relationships, inductive learning
2. **Instruction-Tuned Embeddings (25%)**: Zero-shot semantic understanding
3. **Co-occurrence Embeddings (20%)**: Node2Vec/PecanPy on tournament decks
4. **Visual Embeddings (20%)**: SigLIP 2 vision model for card image similarity
5. **Jaccard Similarity (15%)**: Direct co-occurrence patterns
6. **Functional Tags (10%)**: Role-based similarity (removal, draw, ramp, etc.)

**Pipeline**:
```
Tournament Decks → Graph Construction → Embedding Training → Fusion → API
```

**Key Components**:
- `src/ml/api/api.py` - FastAPI server
- `src/ml/similarity/fusion.py` - Multi-signal fusion
- `src/ml/deck_building/deck_completion.py` - Deck completion algorithm
- `data/graphs/incremental_graph.json` - Co-occurrence graph

---

## API Reference

Base URL: `http://localhost:8000/v1`

### Similarity Search

```bash
# Simple search
GET /cards/{name}/similar?mode=fusion&k=10

# Advanced search with options
POST /similar
{
  "query": "Lightning Bolt",
  "mode": "fusion",
  "use_case": "substitute",
  "top_k": 10,
  "game": "magic",
  "format": "Modern"
}
```

### Deck Operations

```bash
# Complete a deck
POST /deck/complete
{
  "game": "magic",
  "deck": {...},
  "target_main_size": 60
}

# Apply deck modifications
POST /deck/apply_patch
{
  "game": "magic",
  "deck": {...},
  "patch": {"ops": [...]}
}

# Get suggestions
POST /deck/suggest_actions
{
  "game": "magic",
  "deck": {...},
  "top_k": 5
}
```

### Card Search

```bash
# Search by prefix
GET /cards?prefix=Light&limit=10

# Full-text search
GET /search?q=lightning&limit=10
```

See `http://localhost:8000/docs` for complete API documentation with schemas.

---

## Data

### Current Dataset

| Game | Cards | Tournament Decks |
|------|-------|------------------|
| Magic: The Gathering | 35,400 | 55,293 |
| Pokemon | 3,000 | 1,208 |
| Yu-Gi-Oh | 13,930 | 1,500 |

**Total**: 52,330 cards, 56,521 decks

### Data Setup

Data files are not included in the repository. Options:

1. **Download from S3** (if you have access):
   ```bash
   aws s3 sync s3://games-collections/embeddings/ data/embeddings/
   ```

2. **Generate from raw data**:
   ```bash
   just extract-mtg
   uv run --script scripts/data_processing/unified_export_pipeline.py
   ```

See `data/README.md` for detailed data structure and lineage.

---

## Performance

**Current**: P@10 = 0.088 (co-occurrence baseline)
**Target**: P@10 = 0.15-0.20 (hybrid system, in development)

**Evaluation**:
- Test sets: MTG (38 queries), Pokemon (10), Yu-Gi-Oh (13)
- Metrics: Precision@K, MRR, NDCG
- Methodology: Temporal splits (train <2024, test 2024+)

```bash
# Run evaluation
just eval-hybrid-local
```

Results: `experiments/evaluation_results/`

---

## Development

### Testing

```bash
just test          # All tests
just test-quick    # Fast tests only
just test-api      # API tests
just test-e2e      # End-to-end tests
```

### Code Quality

```bash
just lint          # Run Ruff
just format        # Auto-format code
```

### Training

```bash
# Local training (CPU, slow)
just train-hybrid-full-local

# AWS training (GPU, requires instance ID)
just train-hybrid-full-aws <instance-id>
```

**Note**: Training requires `decks_all_final.jsonl` and `incremental_graph.json`. GNN training requires GPU.

### Enrichment

Add functional tags and metadata:

```bash
just enrich-mtg        # Magic: The Gathering
just enrich-pokemon     # Pokemon
just enrich-yugioh      # Yu-Gi-Oh
```

---

## Project Structure

```
decksage/
├── src/ml/           # ML code (embeddings, fusion, API)
├── src/backend/      # Go backend (data processing)
├── scripts/          # Utility scripts
├── tests/            # Integration tests
├── data/             # Data files (not in repo)
├── experiments/      # Evaluation results
└── docs/             # Documentation
```

**Key Files**:
- `src/ml/api/api.py` - FastAPI server
- `src/ml/similarity/fusion.py` - Multi-signal fusion
- `src/ml/deck_building/deck_completion.py` - Deck completion
- `justfile` - All workflow commands
- `docs/quick-reference.md` - Daily workflow guide

---

## Data Lineage

Data flows through 7 orders (0-6):

```
Order 0: Raw data (scraped decks)
  ↓
Order 1: Processed decks (validated, normalized)
  ↓
Order 2: Co-occurrence pairs
  ↓
Order 3: Graph construction
  ↓
Order 4: Embeddings (Node2Vec, E5, GraphSAGE)
  ↓
Order 5: Test sets (ground truth)
  ↓
Order 6: Annotations (training data)
```

Each order depends only on previous orders. All derived data can be regenerated.

---

## Troubleshooting

**API won't start**:
- Check embeddings exist: `ls data/embeddings/*.wv`
- Check port is free: `lsof -i :8000`
- Check API readiness: `curl http://localhost:8000/ready`

**Card not found**:
- API returns suggestions for similar names
- Card must be in vocabulary (check spelling, case-sensitive)
- Try different search modes: `embedding`, `jaccard`, `fusion`

**No similar results**:
- Card may be too new (requires retraining)
- Try `--mode fusion` for best results
- Check API status: `curl http://localhost:8000/ready`

**Tests failing**:
- Run `just test-quick` for fast feedback
- Check `tests/` and `src/ml/tests/` both exist
- Ensure dependencies installed: `uv sync --extra dev`

---

## Known Limitations

- **Performance plateau**: Co-occurrence alone maxes at P@10 ≈ 0.08 (hybrid system targets 0.15-0.20)
- **Test set size**: Limited test sets (38 MTG, 10 Pokemon, 13 Yu-Gi-Oh queries)
- **New cards**: Require retraining (instruction-tuned embeddings handle zero-shot better)
- **Pokemon**: Limited to 3,000 cards due to API pagination
- **Yu-Gi-Oh**: Using card IDs (needs mapping to names)

---

## Documentation

- [`docs/quick-reference.md`](docs/quick-reference.md) - Daily workflow guide
- [`docs/priority-matrix.md`](docs/priority-matrix.md) - Development priorities
- [`data/README.md`](data/README.md) - Data structure and lineage
- [`src/ml/annotation/README.md`](src/ml/annotation/README.md) - Annotation system
- [`src/ml/knowledge/README.md`](src/ml/knowledge/README.md) - Game knowledge system

---

## Contributing

1. Read `docs/quick-reference.md` for workflow
2. Run tests: `just test`
3. Check code quality: `just lint`
4. Format code: `just format`
5. Pre-commit hooks run automatically

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Citation

If you use DeckSage in research, please cite:

```bibtex
@software{decksage2025,
  title = {DeckSage: ML-Powered Card Similarity for Trading Card Games},
  author = {Arc Labs},
  year = {2025},
  url = {https://github.com/arclabs561/decksage}
}
```
