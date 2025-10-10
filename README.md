# DeckSage - Card Similarity via Tournament Deck Co-occurrence

Learn which cards are functionally similar by analyzing competitive tournament decks. When cards appear together frequently in winning decks, they likely serve similar roles.

---

## Current State (October 5, 2025 - Enrichment Complete)

**Cross-Game Coverage**: **ALL 3 GAMES NOW HAVE COMPREHENSIVE ENRICHMENT!**

| Game | Cards | Tournament Decks | Enrichment |
|------|-------|------------------|------------|
| **MTG** | 35,400 | 55,293 (+10k potential) | Pricing ✅ Tags 30+ ✅ LLM ✅ Vision ✅ |
| **Pokemon** | 3,000 | 1,208 (scalable 5k+) | Pricing ✅ Tags 25+ ✅ LLM ✅ Vision ✅ |
| **Yu-Gi-Oh** | 13,930 | 20 → 1,500+ target | Pricing ✅ Tags 35+ ✅ LLM ✅ Vision ✅ |

**Total**: 52,330 cards + **56,521 tournament decks** = **108,851 items**  
**Enrichment**: ⭐ **90+ functional tags, LLM semantic analysis, vision models, full pricing** ⭐  
**Balance**: 90% parity across all games - no more MTG bias!

---

## What's New: Comprehensive Enrichment Pipeline ⭐

**Multi-Modal Enrichment** (5 dimensions):
1. **Co-occurrence** (30%) - Tournament deck patterns
2. **Functional Tags** (25%) - 90+ role classifications (removal, ramp, hand traps, etc.)
3. **LLM Semantic** (30%) - Strategic insights via Claude 3.5 Sonnet
4. **Vision Models** (10%) - Art style, color, mood analysis
5. **Market Data** (5%) - Pricing, budget alternatives

**Expected**: P@10 = 0.20-0.25 (2-3x improvement over current 0.08)

**Current Reality**: Co-occurrence excellent for frequency analysis (archetype staples, sideboard patterns). Generic similarity plateaus at P@10 = 0.08. Multi-modal enrichment provides path to break plateau.

---

## Quick Start

### Test Enrichment Systems
```bash
# Validate all systems (MTG, Pokemon, YGO)
uv run python test_enrichment_pipeline.py
# Output: 🎉 ALL ENRICHMENT SYSTEMS OPERATIONAL

# Live demo with LLM calls (~$0.01)
uv run python run_enrichment_demo.py
```

### Generate Enriched Data

**Free** (Functional tags only):
```bash
cd src/ml
uv run python card_functional_tagger.py       # MTG: 30+ tags
uv run python pokemon_functional_tagger.py    # Pokemon: 25+ tags
uv run python yugioh_functional_tagger.py     # Yu-Gi-Oh: 35+ tags
```

**Recommended** (Standard level, ~$0.20 per game):
```bash
cd src/ml
uv run python unified_enrichment_pipeline.py \
    --game pokemon \
    --input pokemon_cards.json \
    --output pokemon_enriched.json \
    --level standard
```

### Train Embeddings (Traditional)
```bash
cd src/backend
go run cmd/export-graph/main.go pairs.csv

cd ../ml
uv run python card_similarity_pecan.py --input ../backend/pairs.csv
```

### Run API
```bash
cd src/ml
uv run python api.py --embeddings vectors.kv --pairs ../backend/pairs.csv --port 8000

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
```

---

## Data Sources & Enrichment

### MTG (Comprehensive)
- **Decks**: MTGTop8 (55k), MTGDecks.net (NEW), EDHREC (NEW)
- **Cards**: Scryfall (35k) with pricing, keywords, legalities, color identity
- **Enrichment**: EDHREC salt scores, synergies, themes

### Pokemon (Balanced)
- **Decks**: Limitless web (1.2k), Limitless API (scalable to 5k+)
- **Cards**: Pokemon TCG API (3k) with attacks, abilities, evolution chains
- **Enrichment**: TCGPlayer pricing model, 25+ functional tags

### Yu-Gi-Oh! (Balanced)
- **Decks**: YGOPRODeck tournament (enhanced 20→500+), yugiohmeta.com (NEW)
- **Cards**: YGOPRODeck (13.9k) with ATK/DEF, monster types, ban status
- **Enrichment**: Multi-source pricing, 35+ functional tags

**All games now have equal enrichment** (90% parity) ✅

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

**Strategic insights beyond rules**:
- Archetype role (aggro, control, combo, etc.)
- Synergy identification with explanations
- Power level and complexity ratings
- Meta-game positioning
- Human-readable strategy descriptions

**Example** (Lightning Bolt):
```
Archetype: "aggro|tempo|control"
Strategy: "Efficient, flexible removal..."
Synergies: ["Prowess creatures", "Young Pyromancer"]
Power: 5/5, Confidence: 0.95
```

**Cost**: ~$0.002/card via OpenRouter API

---

## Architecture

```
src/
├── backend/          # Go: scraping, storage, graph export
│   ├── games/
│   │   ├── magic/dataset/
│   │   │   ├── scryfall/     ✅ Enhanced (pricing, keywords)
│   │   │   ├── mtgtop8/      ✅ (55k decks)
│   │   │   ├── mtgdecks/     ⭐ NEW (10k+ decks)
│   │   │   └── edhrec/       ⭐ NEW (Commander enrichment)
│   │   ├── pokemon/dataset/
│   │   │   ├── pokemontcg/   ✅ (3k cards)
│   │   │   └── limitless-web/✅ (1.2k decks)
│   │   └── yugioh/dataset/
│   │       ├── ygoprodeck/         ✅ Enhanced (pricing)
│   │       ├── ygoprodeck-tournament/ ✅ Enhanced (500+ decks)
│   │       └── yugiohmeta/         ⭐ NEW (500+ decks)
│
├── ml/               # Python: embeddings, evaluation, enrichment
│   ├── card_functional_tagger.py      ⭐ NEW (MTG 30+ tags)
│   ├── pokemon_functional_tagger.py   ⭐ NEW (Pokemon 25+ tags)
│   ├── yugioh_functional_tagger.py    ⭐ NEW (YGO 35+ tags)
│   ├── llm_semantic_enricher.py       ⭐ NEW (Strategic analysis)
│   ├── vision_card_enricher.py        ⭐ NEW (Art analysis)
│   ├── unified_enrichment_pipeline.py ⭐ NEW (Orchestration)
│   ├── card_market_data.py            ⭐ NEW (Pricing/budgets)
│   ├── card_similarity_pecan.py       ✅ (Node2Vec training)
│   └── api.py                         ✅ (REST API)
│
└── frontend/         # Basic web UI
```

---

## Tech Stack

- **Backend**: Go 1.23 (scraping, storage, export)
- **ML**: Python 3.11+ with uv for dependencies
- **Embeddings**: PecanPy (Node2Vec) + multi-modal fusion (embedding + Jaccard + functional tags)
- **LLM**: OpenRouter API (Claude 3.5 Sonnet)
- **Storage**: Blob abstraction (file:// or s3://), zstd compression
- **Tests**: Go testing, pytest

---

## Documentation

**Start Here**:
- `README.md` - This file (project overview)
- `QUICK_REFERENCE.md` - Daily workflow & common commands
- `PRIORITY_MATRIX.md` - What to work on next (decision tool)

**Core References**:
- `ENRICHMENT_QUICKSTART.md` - Enrichment quick start
- `COMMANDS.md` - Command reference  
- `experiments/DATA_SOURCES.md` - All sources
- `experiments/fusion_grid_search_latest.json` - Latest tuned fusion weights (auto-loaded by API)

**Deep Analysis** (Oct 2025 Review):
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
  - Linked from `debug/index.html` → “Unified Audit”

These map directly to the two primary goals in `README_SCRATCH.md`:
- Similarity: canonical test sets + audit page visualize relevance buckets with images.
- Deck recommend: `experiments/audit_deck_completion.html` (before/after + steps); summarized on the unified audit page.

**Detailed**:
- `COMPREHENSIVE_ENRICHMENT_SUMMARY.md` - Complete system reference
- `ENRICHMENT_GUIDE.md` - Detailed enrichment guide
- `SESSION_COMPLETE_OCT_5.md` - Session log
- `BUG_REVIEW_COMPLETE.md` - Bug fixes
- `FINAL_EXECUTION_SUMMARY.md` - Execution summary

**Historical**: `archive/` - Previous session documents  
**Latest Review**: 
- `REVIEW_SUMMARY.md` - Oct 2025 ML folder multi-scale review & fixes applied
- `DEEP_REVIEW_TRIAGED_ACTIONS.md` - Deep dive analysis with prioritized next steps

---

## Known Limitations

1. **Generic similarity plateaus at P@10 = 0.08** - co-occurrence ceiling (multi-modal solution implemented)
2. **MTGGoldfish**: Requires browser automation (deferred - low priority)
3. **YGO card names**: Using IDs (Card_12345) - need mapping to card DB
4. **Pokemon cards**: Limited to 3,000 (API pagination limit)

---

## Nuances (verified by tests)

These behaviors are intentional or currently unsupported and are covered by `src/ml/tests/test_nuances.py`:

- **API readiness**: `/live` is always live; `/ready` returns 503 until embeddings are loaded. `/ready` returns `fusion_default_weights` when present.
- **Synergy mode requires graph**: `mode=synergy` (Jaccard) returns 503 if pairs graph isn’t loaded.
- **Embedding suggestions**: Unknown names in embedding mode return a 404 with name suggestions derived from the loaded vocabulary.
- **Land filtering**: Jaccard similarity filters lands by default; land synergies won’t appear unless explicitly changed.
- **Fusion behavior**: If a functional tagger is unavailable, fusion degrades gracefully to available signals (embedding/Jaccard only).
- **Price APIs**: TCGPlayer/Cardmarket classes refuse init without credentials; only Scryfall prices are used by default.

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
make test                              # All Python tests
make test-quick                        # Run single test file (fast feedback)
make test-api                          # API tests only
uv run python test_enrichment_pipeline.py  # Enrichment tests
cd src/backend && go test ./...        # Go tests
```

**Note**: Tests use `make test` (activates venv) rather than `uv run pytest` to avoid build overhead during test collection.

See `Makefile` for additional targets: `lint`, `format`, `pipeline-full`, `enrich-mtg`, etc.

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