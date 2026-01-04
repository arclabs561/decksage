# DeckSage - Card Similarity via Tournament Deck Co-occurrence

Find functionally similar cards by analyzing tournament decks. Cards that appear together frequently in winning decks likely serve similar roles.

**Use cases**: Find budget alternatives, discover synergies, complete partial decks, understand meta relationships.

**Example**: If "Lightning Bolt" and "Chain Lightning" appear together in 200+ tournament decks, they're functionally similar (both are efficient red removal).

**License**: MIT (see [LICENSE](LICENSE))

---

## Installation

**Prerequisites**:
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Go 1.23+ (optional, only needed for scraping new deck data)

**Setup**:
```bash
git clone <repo-url>
cd decksage
uv sync                    # Install Python dependencies
uv sync --extra embeddings # Optional: for training embeddings

# Install pre-commit hooks (catches errors early during development)
./scripts/setup-dev.sh
# OR: just pre-commit-install
```

**Pre-commit Hooks** (automatically catch errors on commit/push):
- Python linting & formatting (Ruff)
- Go linting (golangci-lint)
- Shell script linting (shellcheck)
- YAML/JSON/TOML validation
- Data lineage validation
- Fast tests on push

---

## Current State

| Game | Cards | Decks | Enrichment |
|------|-------|-------|------------|
| MTG | 35,400 | 55,293 | Pricing, 30+ tags, LLM |
| Pokemon | 3,000 | 1,208 | Pricing, 25+ tags, LLM |
| Yu-Gi-Oh | 13,930 | 1,500 | Pricing, 35+ tags, LLM |

Total: 52,330 cards, 69,000 tournament decks  
Enrichment: 90+ functional tags, LLM semantic analysis, pricing

---

## Hybrid Embedding System

Combines 5 signals (weights shown):
1. **GNN Embeddings (30%)** - GraphSAGE learns multi-hop relationships
   - Example: "Lightning Bolt" → "Chain Lightning" (direct) → "Shock" (2-hop via shared decks)
2. **Instruction-Tuned (25%)** - E5-base-v2 for semantic similarity
   - Example: "Find removal spell" query matches "Lightning Bolt" and "Swords to Plowshares"
3. **Co-occurrence (20%)** - Node2Vec on deck co-occurrence graph
   - Example: Cards appearing in same 200+ decks get similar embeddings
4. **Jaccard (15%)** - Direct deck overlap percentage
   - Example: 50 shared decks / 100 total = 0.5 similarity
5. **Functional Tags (10%)** - Role-based matching
   - Example: Both tagged "removal" → +0.1 similarity boost

**Performance**: P@10 = 0.08 (co-occurrence only) → 0.15-0.20 target (hybrid)

---

## Quick Start

### 1. Start API Server
```bash
./scripts/start_api.sh
# or
python3 -m src.ml.api.api --embeddings data/embeddings/magic_128d_test_pecanpy.wv --port 8000
```

**Note**: If embeddings file doesn't exist, `start_api.sh` will list available files. Download embeddings from S3 or train your own (see Development section).

### 2. Find Similar Cards

**CLI**:
```bash
uv sync  # Installs 'decksage' command (first time only)
decksage similar "Lightning Bolt" --k 5
```

**Output**:
```
Similar to: Lightning Bolt
Card                                    Similarity
---------------------------------------- -----------
Chain Lightning                         0.8700
Shock                                   0.8200
Lava Spike                              0.7900
Rift Bolt                               0.7600
Burst Lightning                         0.7400
```

**API**:
```bash
curl "localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=fusion&k=5"
```

**Response**:
```json
{
  "query": "Lightning Bolt",
  "results": [
    {"card": "Chain Lightning", "similarity": 0.87},
    {"card": "Shock", "similarity": 0.82},
    {"card": "Lava Spike", "similarity": 0.79},
    {"card": "Rift Bolt", "similarity": 0.76},
    {"card": "Burst Lightning", "similarity": 0.74}
  ]
}
```

**Error example** (card not found):
```json
{
  "detail": "Card 'Lightning Boltz' not found. Suggestions: ['Lightning Bolt', 'Chain Lightning', 'Lightning Helix']"
}
```

### 3. Search Cards
```bash
decksage search "lightning" --output json
curl "localhost:8000/v1/search?q=lightning&limit=10"
```

---

## Enrichment

### Functional Tags (Rule-Based)

**MTG example** - "Lightning Bolt":
```json
{
  "removal": true,
  "instant": true,
  "burn": true,
  "targeted": true
}
```

**Pokemon example** - "Charizard VMAX":
```json
{
  "heavy_hitter": true,
  "rule_box": true,
  "evolution": true
}
```

### LLM Semantic Enrichment

**Example output** for "Lightning Bolt":
```json
{
  "semantic_features": {
    "archetype": "aggro|tempo|control",
    "strategy": "Efficient, flexible removal. Instant speed allows reactive play.",
    "synergies": ["Prowess creatures", "Young Pyromancer"],
    "power_level": 5,
    "llm_confidence": 0.95
  }
}
```

Cost: ~$0.002/card via OpenRouter API

---

## Architecture

**Data Flow**:
1. Scrape tournament decks → `data/processed/decks_all_final.jsonl`
   - Example: 55,293 MTG decks from MTGTop8, MTGDecks.net
2. Build co-occurrence graph → `data/graphs/incremental_graph.json`
   - Example: "Lightning Bolt" co-occurs with "Chain Lightning" in 200+ decks → edge weight 200
3. Train embeddings:
   - Co-occurrence: Node2Vec (PecanPy) → 128-dim vectors
   - Instruction-tuned: E5-base-v2 (zero-shot, no training needed)
   - GNN: GraphSAGE (PyTorch Geometric) → learns 2-hop relationships
4. Fusion → Weighted combination: `0.30*GNN + 0.25*Instruction + 0.20*Co-occurrence + 0.15*Jaccard + 0.10*Tags`
5. API → Serve similarity queries via FastAPI

**Key Files**:
- `src/backend/` - Go scraping, storage
- `src/ml/similarity/` - Embedding models
- `src/ml/api/api.py` - REST API
- `data/graphs/incremental_graph.json` - Co-occurrence graph (~100K nodes, ~1M edges)

---

## Tech Stack

- **Backend**: Go (scraping, storage)
- **ML**: Python 3.11+ (uv for deps)
- **Embeddings**: PecanPy (Node2Vec), E5-base-v2, PyTorch Geometric (GraphSAGE)
- **LLM**: OpenRouter API (Claude 3.5 Sonnet)
- **Storage**: S3 (`s3://games-collections/`), zstd compression

---

## Documentation

- `docs/QUICK_REFERENCE.md` - Daily workflow
- `docs/PRIORITY_MATRIX.md` - What to work on next
- `data/README.md` - Data structure

---

## Evaluation

**Metrics**: P@K (Precision at K), MRR, NDCG

**Example**: P@10 = 0.08 means 8% of top-10 results are relevant (current baseline)

**Test sets**: 
- MTG: 38 queries (canonical) or 940 queries (unified)
- Pokemon: 10 queries
- Yu-Gi-Oh: 13 queries

**Important**: Check vocabulary coverage before evaluation. Many embeddings don't contain all test query cards, causing evaluations to skip queries. Use embeddings with ≥80% coverage.

**Diagnostic Tools**:
```bash
# Check vocabulary coverage
uv run scripts/diagnostics/fix_evaluation_coverage.py

# Validate data pipeline
uv run scripts/diagnostics/validate_data_pipeline.py
```

**Temporal splits**: Train on decks before 2024, test on 2024+ (prevents data leakage)

**Ablation**: Test each component separately to measure contribution

---

## Known Limitations

- Co-occurrence plateaus at P@10 = 0.08 (hybrid system targets 0.15-0.20)
- Pokemon cards: Limited to 3,000 (API pagination)
- YGO card names: Using IDs (Card_12345) - needs mapping
- New cards: Require retraining embeddings (instruction-tuned handles zero-shot)

---

## Troubleshooting

**API won't start**:
- Check embeddings file exists: `ls data/embeddings/*.wv`
- Check port 8000 is free: `lsof -i :8000`
- See `./scripts/start_api.sh` for error messages

**Card not found**:
- API returns 404 with suggestions (try one of the suggested names)
- Card must exist in embeddings vocabulary
- Check card name spelling (case-sensitive)

**No similar results**:
- Card may be too new (not in training data)
- Try different mode: `--mode fusion` (combines all signals)
- Check embeddings are loaded: `curl localhost:8000/ready`

---

## Development

**Tests**:
```bash
just test          # All Python tests
just test-quick    # Single file (fast feedback)
cd src/backend && go test ./...  # Go tests
```

**Training** (optional):
```bash
# Local (CPU, slow)
just train-hybrid-full-local

# AWS (GPU, recommended)
just train-aws-create
just train-hybrid-full-aws <instance-id>
```

**Enrichment**:
```bash
# Functional tags (free, rule-based)
cd src/ml
uv run python card_functional_tagger.py        # MTG
uv run python pokemon_functional_tagger.py    # Pokemon
uv run python yugioh_functional_tagger.py     # Yu-Gi-Oh

# LLM enrichment (requires API key, ~$0.002/card)
# See scripts/rapidapi_enrichment.py or use pydantic-ai directly
```

## Data Lineage

**Orders**: 0 (raw) → 1 (decks) → 2 (pairs) → 3 (graph) → 4 (embeddings) → 5 (test sets) → 6 (annotations)

**Example flow**:
- **Order 0**: Raw scraped data from MTGTop8, Scryfall, etc.
- **Order 1**: `data/processed/decks_all_final.jsonl` (normalized deck lists)
- **Order 2**: `data/processed/pairs_large.csv` (card co-occurrence pairs)
- **Order 3**: `data/graphs/incremental_graph.json` (graph structure)
- **Order 4**: `data/embeddings/magic_128d_pecanpy.wv` (trained embeddings)
- **Order 5**: `experiments/test_set_canonical_magic.json` (evaluation queries)
- **Order 6**: `annotations/batch_001_initial.yaml` (human similarity judgments)

Each order depends only on previous. All derived data can be regenerated from primary sources.

**Example file sizes**:
- Order 1: `decks_all_final.jsonl` (~241 MB, 69K decks)
- Order 2: `pairs_large.csv` (~265 MB, 7.5M pairs)
- Order 3: `incremental_graph.json` (~3 MB, ~100K nodes, ~1M edges)
- Order 4: `magic_128d_pecanpy.wv` (~1 MB, 35K cards, 128-dim vectors)

