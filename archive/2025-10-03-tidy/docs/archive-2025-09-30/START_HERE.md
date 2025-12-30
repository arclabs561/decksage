# DeckSage - START HERE

**Last Updated**: 2025-09-30  
**Status**: Architecture Validated, ML Pipeline Working, Data Needs Diversity

---

## Quick Start

### Run Tests

```bash
cd src/backend
go test ./...
# Expected: 24/24 tests passing in ~3 seconds
```

### Build Similarity Graph & Train Embeddings

```bash
# 1. Export clean deck-only graph
cd src/backend
go run ./cmd/export-decks-only data-full/games/magic pairs_decks.csv

# 2. Train embeddings (Python 3.12 required)
cd ../ml
uv venv --python 3.12
source .venv/bin/activate
uv pip install pecanpy pandas matplotlib scikit-learn

# 3. Run similarity experiment
.venv/bin/python card_similarity_pecan.py \
  --input ../backend/pairs_decks.csv \
  --query "Lightning Bolt" "Brainstorm" \
  --visualize
```

---

## What This Does

**DeckSage** = Multi-game card similarity platform

1. **Extract** - Scrape card game websites (MTG, soon Yu-Gi-Oh!)
2. **Transform** - Build card co-occurrence graphs
3. **Embed** - Train Node2Vec for similarity search
4. **Search** - Find similar cards, recommend deck additions

**Currently**: MTG fully implemented and validated

---

## Current State

### ✅ What Works

- Multi-game architecture (proven with MTG)
- 4 MTG data sources (Scryfall, MTGTop8, Goldfish, Deckbox)
- Co-occurrence transform (deck-only, clean)
- Node2Vec embeddings (PecanPy, validated)
- Similarity search (semantically accurate)
- All tests passing

### ⚠️ What Needs Work

- **Format imbalance**: 44 Legacy vs 16 Modern decks
- **Missing cards**: Tarmogoyf, Ragavan, Lava Spike
- **Archetype clustering**: Need diverse tournament sources
- **Data strategy**: Need balanced extraction plan

### 📋 Next Steps

1. Extract 50+ diverse Modern decks
2. Re-train with balanced data
3. Add Yu-Gi-Oh! support
4. Build REST API + Web UI

---

## Read This First

### For Understanding Architecture

- `ARCHITECTURE.md` - System design
- `ADDING_A_NEW_GAME.md` - How to add games
- `games/game.go` - Universal types (code)

### For Understanding Data Quality

- `EXPERT_CRITIQUE.md` - ⭐ **Domain expert validation**
- `CRITICAL_ANALYSIS.md` - Issues discovered
- `SYNTHESIS_AND_PATH_FORWARD.md` - Strategic analysis

### For Running Experiments

- `ML_EXPERIMENT_COMPLETE.md` - End-to-end experiment
- `ml/card_similarity_pecan.py` - Working script
- `transform/cardco/README.md` - Transform pipeline

### For Current Status

- `SESSION_2025_09_30_COMPLETE.md` - ⭐ **Latest session**
- `WHATS_GOING_ON.md` - Quick overview
- `TESTING_GUIDE.md` - Test infrastructure

---

## Key Insights

1. **Architecture is solid** - Multi-game design proven ✅
2. **ML pipeline works** - Node2Vec embeddings validated ✅
3. **Data diversity matters** - 16 decks insufficient ⚠️
4. **Expert validation critical** - Caught contamination issues ⚠️
5. **Clean data > fancy algorithm** - Simple node2vec works great ✅

---

## Critical Finding

**Set contamination**: Original graph included card sets (printing), which created 36.5% meaningless edges.

**Fixed**: Deck-only filtering  
**Result**: Embeddings now match expert MTG knowledge

**Grade**: Contaminated (6/10) → Clean (8.5/10)

---

## Tools Used

- **Go 1.23** - Data extraction & processing
- **Python 3.12** - ML training
- **uv** - Fast package management (10-100x faster than pip)
- **PecanPy** - Node2Vec implementation (peer-reviewed, Bioinformatics 2021)
- **Gensim** - Word embeddings framework

---

## Commands Cheat Sheet

```bash
# Tests
cd src/backend && go test ./...

# Analyze graph structure
cd src/backend && go run ./cmd/analyze-graph data-full/games/magic

# Export clean graph
cd src/backend && go run ./cmd/export-decks-only data-full/games/magic decks.csv

# Train embeddings
cd src/ml && .venv/bin/python card_similarity_pecan.py --input ../backend/decks.csv

# Query cards
cd src/ml && .venv/bin/python card_similarity_pecan.py \
  --input ../backend/decks.csv --query "Lightning Bolt"
```

---

**Questions?** Read `SESSION_2025_09_30_COMPLETE.md` for full session report.

**Want to contribute?** Read `ADDING_A_NEW_GAME.md` for implementation guide.

**Found issues?** Read `EXPERT_CRITIQUE.md` for known limitations.
