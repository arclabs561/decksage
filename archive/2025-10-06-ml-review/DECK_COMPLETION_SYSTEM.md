# Deck Completion System

## Overview

Complete deck-building system with JSON-Patch-style action interface, policy-optimizable action space, and REST API for incomplete deck completion across MTG/Pokemon/YGO.

**Status**: Production-ready with real-data validation  
**Tests**: 22/22 passing  
**Performance**: 450ms avg latency under 20× concurrent load  
**Data**: 4,660 cards, 380K edges, 57K decks  

---

## Architecture

### Core Components

1. **DeckPatch** (`src/ml/deck_patch.py`)
   - JSON-Patch-like operations: add_card, remove_card, replace_card, move_card, set_format, set_archetype
   - Atomic transaction: all ops validate or all fail
   - Lenient mode: allows partial decks (size constraints relaxed) while enforcing copy limits
   - Strict mode: enforces format rules + optional banlist legality
   - Structured errors with codes, locs, and constraints_relaxed metadata

2. **DeckCompletion** (`src/ml/deck_completion.py`)
   - Candidate generation from similarity (embedding/jaccard/fusion)
   - Budget filtering with fallback to unpriced cards
   - Functional coverage boosting (diminishing returns, per-tag weights)
   - Curve heuristics (CMC distribution optimization)
   - CardResolver for alias/split-card canonicalization

3. **DeckCompletionEnv** (`src/ml/deck_env.py`)
   - Minimal Gym-like interface for RL/planning
   - reset(deck) → observation
   - step(action) → (deck, reward, done, info)
   - Compatible with future policy optimization

4. **REST API** (`src/ml/api.py`)
   - POST /v1/deck/apply_patch - atomic patch application
   - POST /v1/deck/suggest_actions - top-K additions with rationales
   - POST /v1/deck/complete - greedy completion to target size
   - All endpoints return metrics (timings, candidate counts, flags)

---

## Rigorous Testing Results

### Real Data Performance (Node2Vec 64D, 4.6K cards)

```
Trained: 64D embeddings from 380K edges in ~5s
Loaded: 4,660 cards, 6,623 graph nodes

Similarity Performance:
- Embedding:  ~0-5ms per query
- Jaccard:    ~80ms per query  
- Fusion:     ~200-400ms per query (tagger overhead)

Deck Completion:
- Suggest 20 actions: ~400ms (60 candidates after filtering)
- Complete to 40 cards: 32 steps in 80s (2.5s/step avg)
- Final deck: valid, sensible synergy (mill/blue cards for Archive Trap deck)

Concurrent Load (20 threads, fusion mode):
- 20/20 requests succeeded
- 450ms avg latency per request
- No races or crashes
```

### Functional Validation

**Embedding Mode**: Lightning Bolt → Chain Lightning, Thermo-Alchemist, Fireblast  
**Jaccard Mode**: Iono → Boss's Orders, Night Stretcher, Ultra Ball  
**Fusion Mode**: Sensitive to weights (B over C when embed-heavy, C over B when jaccard-heavy)  
**Strict vs Lenient**: Strict rejects size violations; lenient returns partial with `constraints_relaxed=['size']`  

---

## API Usage

### Start Service

```bash
# With env config (recommended)
export EMBEDDINGS_PATH=/path/to/model.wv
export PAIRS_PATH=/path/to/pairs.csv
export ATTRIBUTES_PATH=/path/to/attrs.csv  # optional for faceted Jaccard
uv run uvicorn src.ml.api:app --reload

# Or direct
uv run python -m src.ml.api --embeddings data/embeddings/test_quick_pecanpy.wv --pairs src/backend/pairs.csv
```

### Example Requests

```bash
# Suggest actions with coverage boost
curl -X POST http://localhost:8000/v1/deck/suggest_actions \
  -H "Content-Type: application/json" \
  -d '{
    "game": "magic",
    "deck": {
      "deck_id": "ex",
      "format": "Modern",
      "partitions": [{"name":"Main","cards":[{"name":"Lightning Bolt","count":4}]}]
    },
    "top_k": 20,
    "coverage_weight": 0.15,
    "budget_max": 10.0,
    "mode": "fusion"
  }'

# Complete deck to 60 cards
curl -X POST http://localhost:8000/v1/deck/complete \
  -H "Content-Type: application/json" \
  -d '{
    "game": "magic",
    "deck": { /* partial deck */ },
    "target_main_size": 60,
    "mode": "fusion",
    "coverage_weight": 0.15,
    "strict_size": false
  }'
```

---

## Features

### Budget-Aware Completion
- `budget_max`: maximum price per card
- Filters expensive candidates
- Falls back to unpriced cards if no affordable options
- Uses `MarketDataManager` (Scryfall price cache)

### Functional Coverage
- `coverage_weight`: bias toward cards adding new tags
- Per-tag weights via `tag_weights` dict
- Diminishing returns to avoid over-diversification
- Uses `FunctionalTagger` (rule-based, 30+ tags)

### Curve Optimization
- `curve_target`: desired CMC distribution (e.g., {1:0.6, 2:0.2, 3:0.2})
- `curve_weight`: small boost for curve-filling cards
- Uses attributes CSV for CMC lookup

### Strict vs Lenient
- Default lenient: allows partial decks during building
- `strict_size=true`: enforces format size requirements
- `check_legality=true`: runs banlist validation
- Returns `constraints_relaxed` metadata

---

## Prerequisites Checklist

✅ **Action schema**: DeckPatch with 6 op types  
✅ **Patch interpreter**: atomic apply with validation  
✅ **Candidate generator**: similarity + legality filtering  
✅ **Budget constraints**: price filtering with fallback  
✅ **Coverage scoring**: functional tag diversity  
✅ **Curve heuristics**: CMC distribution fit  
✅ **API endpoints**: apply/suggest/complete  
✅ **Environment**: Gym-like for future RL  
✅ **Evaluation helpers**: coverage delta, price totals  
✅ **Tests**: unit, property (Hypothesis), API, stress (22 passing)  
✅ **Real-data validation**: Node2Vec, 4.6K cards, sensible suggestions  

---

## Integration with ML Pipeline

### Compatible with Node2Vec (pecanpy)
- Consumes gensim KeyedVectors
- Tested with 64D embeddings from pairs.csv
- Works with any p/q/dim configuration

### Compatible with PyTorch Geometric
- As long as PyG embeddings saved as `.wv` (gensim format)
- API uses same similarity interface
- Fusion normalization keeps PyG and Node2Vec comparable

### Fusion Weights
- Default: embed=0.20, jaccard=0.40, functional=0.40
- Tunable via API request or loaded from `experiments/fusion_grid_search_latest.json`
- Per-modality normalization ensures weight changes have visible effect

---

## Gaps and Future Work

### Performance
- **Tagger build spam**: FunctionalTagger tries to build DB on first use; silence unless coverage_weight > 0 or prebuild at startup
- **Per-request memoization**: cache similarity results within a request to avoid repeated calls
- **Streaming completion**: long completions are opaque; add SSE or chunked responses

### Accuracy
- **PyG attributes**: integrate node features (cmc/type/color) directly into completion scorer
- **Per-tag weights**: expose default weight tables (removal/ramp higher than niche tags)
- **Manabase heuristics**: add color pip tracking and land count targets

### Data Quality
- **Price coverage**: expose price hit rate in metrics; add multi-source fallback
- **Card resolver**: extend with Scryfall oracle IDs and DFC/adventure/meld handling
- **Attributes CSV**: generate from Scryfall JSONs for faceted Jaccard

### Evaluation
- **Completion quality metrics**: synergy score (fusion), functional balance, curve fit
- **Offline training data**: mask real decks to create partial→full tasks for supervised learning
- **Policy optimization**: train bandit/IL/RL on masked completion tasks

---

## Files

**Core**:
- `src/ml/deck_patch.py` (242 lines) - Patch schema + interpreter
- `src/ml/deck_completion.py` (180 lines) - Greedy completion + scoring
- `src/ml/deck_env.py` (80 lines) - Gym-like environment
- `src/ml/card_resolver.py` (70 lines) - Name canonicalization
- `src/ml/completion_eval.py` (59 lines) - Eval helpers
- `src/ml/api.py` (832 lines) - REST API with all endpoints

**Tests**:
- `src/ml/tests/test_deck_patch_and_completion.py` - Patch/greedy/budget
- `src/ml/tests/test_completion_eval.py` - Coverage/price metrics
- `src/ml/tests/test_patch_properties.py` - Hypothesis property tests
- `src/ml/tests/test_api_*.py` - API smoke/fusion/stress/faceted
- Total: 22 tests, all passing

**Integration**:
- `api.py` (root) - Legacy import shim for tests
- Modified `pyproject.toml` - Added hypothesis dev dependency

---

## Quick Start

```bash
# Train embeddings if needed
cd src/ml
uv run python card_similarity_pecan.py \
  --input ../backend/pairs.csv \
  --output magic_quick \
  --dim 64 \
  --mode SparseOTF

# Run tests
cd ../..
uv run pytest -q src/ml/tests/test_deck_patch_and_completion.py

# Start API
export EMBEDDINGS_PATH=data/embeddings/magic_quick_pecanpy.wv
export PAIRS_PATH=src/backend/pairs.csv
uv run uvicorn src.ml.api:app --reload

# Try it
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/v1/similar \
  -H "Content-Type: application/json" \
  -d '{"query":"Lightning Bolt","top_k":10,"mode":"fusion"}'
```

---

## Summary

We built a complete deck-completion system aligned with the goal of policy-optimizable partial deck building:

1. **Action space**: DeckPatch ops with validation
2. **Policy interface**: greedy baseline + environment for future learning
3. **Constraints**: budget, legality, copy limits, format rules
4. **Scoring**: similarity (Node2Vec/PyG) + coverage + curve + budget
5. **API**: REST endpoints with metrics and structured errors
6. **Validation**: 22 tests + real-data stress test + concurrent load
7. **Performance**: <500ms latency, scales to 4.6K cards

**Next**: Train supervised policy on masked decks or use for human-in-the-loop deck builder UI.

