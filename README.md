# DeckSage - Card Similarity via Tournament Deck Co-occurrence

Learn which cards are functionally similar by analyzing competitive tournament decks. When cards appear together frequently in winning decks, they likely serve similar roles.

---

## Current State (January 2025)

| Game | Cards | Tournament Decks | Enrichment |
|------|-------|------------------|------------|
| MTG | 35,400 | 55,293 (+10k potential) | Pricing, 30+ tags, LLM, Vision |
| Pokemon | 3,000 | 1,208 (scalable 5k+) | Pricing, 25+ tags, LLM, Vision |
| Yu-Gi-Oh | 13,930 | 20 → 1,500+ target | Pricing, 35+ tags, LLM, Vision |

Total: 52,330 cards + 69,000 tournament decks = 121,330 items  
Enrichment: 90+ functional tags, LLM semantic analysis, vision models, full pricing  
Balance: 90% parity across all games  
Storage: All data synced to `s3://games-collections/` (880K+ files extracted)

---

## Hybrid Embedding System

Three-component hybrid architecture:
1. Co-occurrence Embeddings (20%) - Node2Vec/PecanPy on tournament deck co-occurrence graph
2. Instruction-Tuned Embeddings (25%) - E5-base-v2 for zero-shot card substitution tasks
3. GNN Embeddings (30%) - GraphSAGE on co-occurrence graph for multi-hop relationships
4. Jaccard Similarity (15%) - Direct co-occurrence overlap
5. Functional Tags (10%) - Role-based similarity (removal, ramp, etc.)

Features:
- Incremental Graph: Continuously updated co-occurrence graph with temporal tracking
- Zero-Shot Capability: Instruction-tuned embeddings handle new cards without retraining
- Inductive Learning: GraphSAGE generates embeddings for unseen nodes via neighbor aggregation
- Update Schedule: Daily incremental updates, weekly GNN retraining, monthly full rebuild

Expected: P@10 = 0.15-0.20 (2-2.5x improvement over current 0.08)

Current: Co-occurrence plateaus at P@10 = 0.08. Hybrid system combines structural (GNN), semantic (instruction-tuned), and statistical (co-occurrence) signals.

---

## Quick Start

### Test Enrichment Systems
```bash
# Validate all systems (MTG, Pokemon, YGO)
uv run python test_enrichment_pipeline.py

# Live demo with LLM calls (~$0.01)
uv run python run_enrichment_demo.py
```

### Generate Enriched Data

Functional tags only (free):
```bash
cd src/ml
uv run python card_functional_tagger.py       # MTG: 30+ tags
uv run python pokemon_functional_tagger.py    # Pokemon: 25+ tags
uv run python yugioh_functional_tagger.py     # Yu-Gi-Oh: 35+ tags
```

Standard level (~$0.20 per game):
```bash
cd src/ml
uv run python unified_enrichment_pipeline.py \
    --game pokemon \
    --input pokemon_cards.json \
    --output pokemon_enriched.json \
    --level standard
```

### Train Hybrid Embeddings

Full Hybrid Training (AWS):
```bash
# Create instance (defaults to g4dn.xlarge for GPU training)
just train-aws-create

# Train full hybrid system (graph + GNN + instruction-tuned)
just train-hybrid-full-aws <instance-id>
# or manually:
./scripts/training/train_hybrid_full_with_runctl.sh aws <instance-id>
```

GNN Training Only:
```bash
# Train GNN embeddings (GraphSAGE)
just train-gnn-aws <instance-id>
# or manually:
./scripts/training/train_hybrid_gnn_with_runctl.sh aws <instance-id>
```

Local Training (for testing):
```bash
# Full hybrid training
just train-hybrid-full-local

# Or step-by-step:
uv run python -m ml.scripts.setup_hybrid_embeddings  # Initial setup
uv run python -m ml.scripts.train_hybrid_full        # Full pipeline
```

Note: Training instances default to `g4dn.xlarge` (GPU-enabled). Smaller instances like `t3.medium` or `t4g.small` are not recommended for training workloads.

Legacy Co-occurrence Only:
```bash
cd src/ml
uv run python card_similarity_pecan.py --input data/processed/pairs_large.csv
```

Traditional (legacy):
```bash
cd src/backend
go run cmd/export-graph/main.go pairs.csv

cd ../ml
uv run python card_similarity_pecan.py --input ../backend/pairs.csv
```

### Run API
```bash
# Quick start
./scripts/start_api.sh
# or
python3 -m src.ml.api.api --embeddings data/embeddings/magic_128d_test_pecanpy.wv --port 8000

# Health
curl -s localhost:8000/live
curl -s localhost:8000/ready

# Query
curl -s "localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=synergy&k=5"

# Fusion (multi-signal)
curl -s "localhost:8000/v1/cards/Lightning%20Bolt/similar?mode=fusion&k=10"
# Optionally override weights (defaults auto-loaded from experiments/fusion_grid_search_latest.json)
curl -s -X POST localhost:8000/v1/similar \
  -H 'Content-Type: application/json' \
  -d '{"query": "Lightning Bolt", "top_k": 10, "use_case": "substitute", "mode": "fusion", "weights": {"embed": 0.2, "jaccard": 0.4, "functional": 0.4}}'

# Hybrid Search (Meilisearch + Qdrant)
curl -s "localhost:8000/v1/search?q=lightning&limit=10&text_weight=0.5&vector_weight=0.5"
```

### CLI (Python)

Install:
```bash
uv sync  # Installs 'decksage' command automatically
```

Use CLI:
```bash
# Find similar cards
decksage similar "Lightning Bolt" --k 5

# Search cards
decksage search "lightning" --output json

# Check API health
decksage health

# List available cards
decksage list --prefix "Light" --limit 20

# Use direct mode (faster, local only - no HTTP overhead)
decksage similar "Lightning Bolt" --direct --k 5

# Remote API
decksage similar "Lightning Bolt" --url http://api.example.com:8000
```

CLI Commands:
- `decksage similar <card>` - Find similar cards
- `decksage search <query>` - Search cards
- `decksage health` - Check API health
- `decksage ready` - Check API readiness
- `decksage list` - List available cards

Via justfile:
```bash
just cli "similar Lightning Bolt --k 5"
just cli "health"
```

Why Python CLI:
- Same ecosystem (no Node.js dependency)
- Direct mode support (faster, no HTTP overhead for local use)
- Consistent with project patterns (`argparse` like all other scripts)
- Lower maintenance (shared dependencies, no type sync issues)

### TypeScript Client (Archived)

Status: Archived on 2025-01-01. Frontend uses direct `fetch()` calls, and Python CLI replaced the TypeScript CLI.

Location: `archive/2025-01-01-cleanup/packages/decksage-ts/`

If needed: Restore from archive for future frontend/Node.js work. The frontend currently uses direct API calls via `fetch()`.

### Run Frontend
```bash
cd src/frontend/deck-recommender
npm install
npm start
# Opens at http://localhost:3000
```

Features:
- Type-ahead search with card images
- Hybrid search (text + semantic)
- Click card image to see similar cards from embeddings
- Expandable result rows with details

---

## Data Sources & Enrichment

### MTG
- Decks: MTGTop8 (55k), MTGDecks.net, EDHREC
- Cards: Scryfall (35k) with pricing, keywords, legalities, color identity
- Enrichment: EDHREC salt scores, synergies, themes

### Pokemon
- Decks: Limitless web (1.2k), Limitless API (scalable to 5k+)
- Cards: Pokemon TCG API (3k) with attacks, abilities, evolution chains
- Enrichment: TCGPlayer pricing model, 25+ functional tags

### Yu-Gi-Oh
- Decks: YGOPRODeck tournament (enhanced 20→500+), yugiohmeta.com
- Cards: YGOPRODeck (13.9k) with ATK/DEF, monster types, ban status
- Enrichment: Multi-source pricing, 35+ functional tags

All games have equal enrichment (90% parity).

---

## Functional Classification

### MTG: 30+ Tags (`card_functional_tagger.py`)
Removal, ramp, tutors, counterspells, board wipes, recursion, protection, evasion, win conditions

### Pokemon: 25+ Tags (`pokemon_functional_tagger.py`)
Heavy hitters, energy acceleration, draw support, disruption, evolution support, rule box cards

### Yu-Gi-Oh: 35+ Tags (`yugioh_functional_tagger.py`)
Hand traps, negation, search, special summon, floodgates, quick effects, OTK enablers

---

## LLM Semantic Enrichment

Strategic insights beyond rules:
- Archetype role (aggro, control, combo, etc.)
- Synergy identification with explanations
- Power level and complexity ratings
- Meta-game positioning
- Human-readable strategy descriptions

Example (Lightning Bolt):
```
Archetype: "aggro|tempo|control"
Strategy: "Efficient, flexible removal..."
Synergies: ["Prowess creatures", "Young Pyromancer"]
Power: 5/5, Confidence: 0.95
```

Cost: ~$0.002/card via OpenRouter API

---

## Architecture

```
src/
├── backend/          # Go: scraping, storage, graph export
│   ├── games/
│   │   ├── magic/dataset/
│   │   │   ├── scryfall/     (pricing, keywords)
│   │   │   ├── mtgtop8/      (55k decks)
│   │   │   ├── mtgdecks/     (10k+ decks)
│   │   │   └── edhrec/       (Commander enrichment)
│   │   ├── pokemon/dataset/
│   │   │   ├── pokemontcg/   (3k cards)
│   │   │   └── limitless-web/ (1.2k decks)
│   │   └── yugioh/dataset/
│   │       ├── ygoprodeck/         (pricing)
│   │       ├── ygoprodeck-tournament/ (500+ decks)
│   │       └── yugiohmeta/         (500+ decks)
│
├── ml/               # Python: embeddings, evaluation, enrichment
│   ├── data/
│   │   └── incremental_graph.py    (Continuous graph updates)
│   ├── similarity/
│   │   ├── gnn_embeddings.py        (GraphSAGE/GCN/GAT)
│   │   ├── instruction_tuned_embeddings.py (E5-base-v2)
│   │   ├── fusion.py                 (Multi-signal fusion)
│   │   └── text_embeddings.py        (Legacy text embeddings)
│   ├── evaluation/
│   │   ├── cv_ablation.py            (CV & ablation framework)
│   │   └── evaluate.py               (Evaluation metrics)
│   ├── scripts/
│   │   ├── train_hybrid_full.py      (Full hybrid training)
│   │   ├── train_hybrid_from_pairs.py (Pairs-based training)
│   │   ├── train_gnn_with_runctl.py  (GNN training)
│   │   ├── update_graph_incremental.py (Graph updates)
│   │   └── evaluate_hybrid_with_runctl.py (Hybrid evaluation)
│   ├── card_functional_tagger.py      (MTG 30+ tags)
│   ├── pokemon_functional_tagger.py   (Pokemon 25+ tags)
│   ├── yugioh_functional_tagger.py    (YGO 35+ tags)
│   ├── card_similarity_pecan.py       (Node2Vec training)
│   └── api.py                         (REST API)
│
└── frontend/         # Basic web UI
```

Data Flow:
1. Scraping → Decks collected from tournament sites
2. Incremental Graph → `IncrementalCardGraph` updates co-occurrence graph
3. Training → Three embedding types trained/initialized:
   - Co-occurrence: Node2Vec on graph
   - Instruction-tuned: E5-base-v2 (zero-shot, no training)
   - GNN: GraphSAGE on graph edgelist
4. Fusion → `WeightedLateFusion` combines all signals
5. API → Serves similarity queries

---

## Tech Stack

- Backend: Go 1.24.9 (scraping, storage, export)
- ML: Python 3.11+ with uv for dependencies
- Embeddings: 
  - Co-occurrence: PecanPy (Node2Vec) on tournament deck graph
  - Instruction-tuned: E5-base-v2 (sentence-transformers) for zero-shot tasks
  - GNN: PyTorch Geometric (GraphSAGE) for multi-hop relationships
  - Fusion: Weighted late fusion combining all signals
- Graph Storage: JSON format (`data/graphs/incremental_graph.json`) for incremental updates
- Training: `runctl` for AWS/local training orchestration
- LLM: OpenRouter API (Claude 3.5 Sonnet) for semantic enrichment
- Storage: Blob abstraction (file:// or s3://), zstd compression
- Tests: Go testing, pytest

---

## Documentation

Start Here:
- `README.md` - This file (project overview)
- `docs/QUICK_REFERENCE.md` - Daily workflow & common commands
- `docs/PRIORITY_MATRIX.md` - What to work on next (decision tool)

Training & Infrastructure:
- Training instances default to `g4dn.xlarge` (GPU-enabled)
- Personal infrastructure (gyarados, alakazam) excluded from training scripts
- Use `scripts/verify_training_status.py` to check training instances
- Use `scripts/analyze_idle_instances.py` to identify idle instances

Core References:
- `ENRICHMENT_QUICKSTART.md` - Enrichment quick start
- `COMMANDS.md` - Command reference  
- `experiments/DATA_SOURCES.md` - All sources
- `experiments/fusion_grid_search_latest.json` - Latest tuned fusion weights (auto-loaded by API)

Deep Analysis (Oct 2025 Review):
- `DEEP_REVIEW_TRIAGED_ACTIONS.md` - Strategic analysis & prioritized next steps
- `REVIEW_SUMMARY.md` - Multi-scale critique & improvements applied

### Datasets & Derived Artifacts (aligned with goals in README_SCRATCH.md)

- Annotations (human/LLM):
  - `annotations/batch_001_initial.yaml` (complete, 5 queries)
  - `annotations/batch_002_expansion.yaml` (LLM draft → human validation)
  - `annotations/batch_auto_generated.yaml` (active selection stubs)
  - `annotations/schema.yaml` (guidelines, scales, types)
  - Metrics/Judgments: `annotations/metrics/*.json`, `annotations/llm_judgments/*.json`

- Canonical test sets (evaluation standard):
  - `experiments/test_set_canonical_magic.json`
  - `experiments/test_set_canonical_yugioh.json`
  - `experiments/test_set_canonical_pokemon.json`
  - Draft batch: `experiments/test_set_batch002.json`

- Derived evaluation artifacts:
  - `experiments/fusion_grid_search_latest.json` (best fusion weights, P@10)
  - `experiments/CURRENT_BEST_magic.json` (baseline snapshot)
  - `experiments/evaluation_report_latest.html` (detailed table)
  - `experiments/EXPERIMENT_LOG_CANONICAL.jsonl` (runs log)

- Human audit (single page):
  - `experiments/audit.html` (images, per‑game sections, averages; no emojis)
  - Linked from `docs/index.html` → "Unified Audit"

These map directly to the two primary goals in `README_SCRATCH.md`:
- Similarity: canonical test sets + audit page visualize relevance buckets with images.
- Deck recommend: `experiments/audit_deck_completion.html` (before/after + steps); summarized on the unified audit page.

Pipeline & Data:
- `PIPELINE_COHERENCE_COMPLETE.md` - Complete pipeline documentation
- `PIPELINE_COHERENCE_SUMMARY.md` - Executive summary
- `data/README.md` - Data directory structure and usage

Hybrid Embedding System:
- `src/ml/evaluation/cv_ablation.py` - Cross-validation and ablation study framework
- Graph storage: JSON format (`data/graphs/incremental_graph.json`) - see modeling perspective below
- Training scripts: `src/ml/scripts/train_hybrid_*.py`
- Evaluation scripts: `src/ml/scripts/evaluate_hybrid_*.py`

Historical: `docs/archive/` - Previous session documents

---

## Modeling Perspective & Best Practices

### Hybrid Embedding Architecture

Our hybrid system combines three complementary embedding approaches:

1. Co-occurrence Embeddings (Node2Vec/PecanPy)
   - Captures statistical patterns from tournament deck co-occurrence
   - Strengths: Archetype staples, sideboard patterns, meta trends
   - Limitations: Requires sufficient data, struggles with new cards

2. Instruction-Tuned Embeddings (E5-base-v2)
   - Zero-shot capability for new cards and tasks
   - Strengths: Semantic understanding, task-specific similarity
   - Limitations: No game-specific knowledge, slower inference

3. GNN Embeddings (GraphSAGE)
   - Multi-hop relationships, structural similarity
   - Strengths: Inductive learning for new nodes, captures complex patterns
   - Limitations: Requires graph structure, training overhead

Fusion Strategy: Weighted late fusion (30% GNN, 25% Instruction, 20% Co-occurrence, 15% Jaccard, 10% Functional) combines strengths while mitigating individual weaknesses.

### Graph Storage

Current Choice: JSON (`data/graphs/incremental_graph.json`)

Rationale:
- Simplicity: Human-readable, easy debugging
- Incremental updates: Straightforward append/merge operations
- Current scale: ~100K nodes, ~1M edges (manageable)
- Operational simplicity: No database overhead

When to Migrate:
- Graph exceeds 10M edges → Consider Parquet (columnar, compressed)
- Need sub-second queries → Consider graph database (Neo4j, ArangoDB)
- Load time >30 seconds → Optimize or migrate format

Storage Location:
- Local: `data/graphs/incremental_graph.json`
- S3: `s3://games-collections/graphs/incremental_graph.json`
- Sync: `just sync-s3` or `scripts/sync_all_to_s3.sh`

### Cross-Validation & Ablation Studies

Temporal Splits: Graph data requires temporal ordering (not random splits) to respect time dependencies and prevent data leakage.

Train/Val/Test Split: 70/15/15 by default, ordered by timestamp.

Cross-Validation: K-Fold CV for hyperparameter tuning, nested CV for final evaluation.

Ablation Studies: Test each component independently:
- Co-occurrence only
- Instruction-tuned only
- GNN only
- All combinations
- Full hybrid system

Metrics Tracked:
- P@K (Precision at K): Primary metric
- MRR (Mean Reciprocal Rank): Ranking quality
- NDCG (Normalized Discounted Cumulative Gain): Position-weighted ranking
- Per-component contributions: Ablation analysis

Usage:
```bash
# Run ablation study
uv run python -m ml.evaluation.cv_ablation \
    --test-set experiments/test_set_canonical_magic.json \
    --graph data/graphs/incremental_graph.json \
    --output experiments/ablation_results.json
```

### Evaluation Best Practices

1. Use Temporal Splits: Never randomize graph data splits
2. Track Multiple Metrics: P@K, MRR, NDCG for comprehensive evaluation
3. Ablation Studies: Understand component contributions
4. Confidence Intervals: Bootstrap or permutation tests for significance
5. Downstream Tasks: Evaluate on substitution, completion, not just similarity

### Data Leakage Prevention

Critical: Always use temporal splits to prevent test data from influencing training.

Leakage Analysis: Run automated leakage detection:
```bash
uv run python -m ml.evaluation.leakage_analysis \
    --graph data/graphs/incremental_graph.json \
    --decks data/processed/decks_all_final.jsonl \
    --test-set experiments/test_set_canonical_magic.json
```

Key Rules:
1. Graph Construction: Only use train/val decks (exclude test period)
2. GNN Training: Train on train/val graph edges only
3. Co-occurrence Training: Filter pairs by timestamp (train/val only)
4. Evaluation: Use train-only graph for Jaccard similarity
5. Temporal Splits: Default in `train_hybrid_full.py` (use `--use-temporal-split`)

See: `LEAKAGE_ANALYSIS.md` for detailed analysis and fixes.

---

## Known Limitations

1. Generic similarity plateaus at P@10 = 0.08 - co-occurrence ceiling (multi-modal solution implemented)
2. MTGGoldfish: Requires browser automation (deferred - low priority)
3. YGO card names: Using IDs (Card_12345) - need mapping to card DB
4. Pokemon cards: Limited to 3,000 (API pagination limit)

---

## Nuances

These behaviors are intentional or currently unsupported and are covered by `src/ml/tests/test_nuances.py`:

- API readiness: `/live` is always live; `/ready` returns 503 until embeddings are loaded. `/ready` returns `fusion_default_weights` when present.
- Synergy mode requires graph: `mode=synergy` (Jaccard) returns 503 if pairs graph isn't loaded.
- Embedding suggestions: Unknown names in embedding mode return a 404 with name suggestions derived from the loaded vocabulary.
- Land filtering: Jaccard similarity filters lands by default; land synergies won't appear unless explicitly changed.
- Fusion behavior: If a functional tagger is unavailable, fusion degrades gracefully to available signals (embedding/Jaccard only).
- Price APIs: TCGPlayer/Cardmarket classes refuse init without credentials; only Scryfall prices are used by default.

Run just these nuances tests:

```bash
uv run pytest src/ml/tests/test_nuances.py -q
```

### Tune fusion weights

```bash
# Merge new annotations into canonical test set first (see annotation bootstrap tools)
uv run python -m ml.fusion_grid_search_runner \
  --embeddings src/ml/vectors.kv \
  --pairs src/backend/pairs.csv \
  --game magic \
  --step 0.1 \
  --top-k 10

# The best weights and score are saved to experiments/fusion_grid_search_latest.json
# Restart the API to auto-load updated weights.
```

---

## Not Doing (Yet)

Moved to `src/ml/experimental/`:
- A-Mem networked experiments
- Memory evolution systems
- Meta-learning across experiments

These are sophisticated but premature. Revisit when P@10 > 0.15 and basics are solid.

---

## Contributing

Run tests. If they pass, the code works:

```bash
just test                              # All Python tests
just test-quick                        # Run single test file (fast feedback)
just test-api                          # API tests only
uv run python test_enrichment_pipeline.py  # Enrichment tests
cd src/backend && go test ./...        # Go tests
```

Note: Tests use `just test` (activates venv) rather than `uv run pytest` to avoid build overhead during test collection.

See `justfile` for additional targets: `lint`, `format`, `pipeline-full`, `enrich-mtg`, etc.

Don't write status documents. Update this README or write tests.

---

## License

[Specify license]

## DeckSage API (CLI)

Run the API (repo layout):

```bash
uvicorn src.ml.api.api:app --reload
python -m src.ml.api.api --embeddings /path/to/model.wv --port 8000
```

Run the API (installed layout):

```bash
uvicorn ml.api.api:app --reload
decksage-api --embeddings /path/to/model.wv --port 8000
```

Environment variables:

- `EMBEDDINGS_PATH`: path to a `.wv` file to auto-load at startup
- `PAIRS_PATH`: optional CSV for co-occurrence graph (enables Jaccard/fusion)
- `ATTRIBUTES_PATH`: optional CSV for attributes (enables faceted Jaccard)
- `CORS_ORIGINS`: comma-separated origins for CORS (default `*`)
- `DECKSAGE_ROOT`: override project root for installed/package layouts

Notes:
- `.env` is loaded early and again during app lifespan; tests may override env.
- Fusion is advertised as available only when graph data is loaded.
## Data Lineage

See [docs/DATA_LINEAGE.md](docs/DATA_LINEAGE.md) for complete documentation.

**Quick Reference:**
- **Order 0**: Primary source data (raw extracted collections)
- **Order 1**: Exported decks (JSONL format)
- **Order 2**: Co-occurrence pairs (CSV)
- **Order 3**: Incremental graph (SQLite/JSON)
- **Order 4**: Embeddings (Word2Vec/GNN models)
- **Order 5**: Test sets (evaluation queries)
- **Order 6**: Annotations (similarity judgments)

Each order depends only on previous orders. All derived data can be regenerated from primary sources.

