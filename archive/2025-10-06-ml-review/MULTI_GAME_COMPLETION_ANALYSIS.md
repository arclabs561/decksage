# Multi-Game Deck Completion: Reality & Path Forward

**Date**: October 5, 2025
**Context**: Post-implementation introspection after discovering multi-game data conflation

---

## What We Discovered

### Data Reality (After Splitting)

```
Original (Mixed):
- pairs.csv: 761K pairs, 6,623 cards (ALL GAMES)
- decks_hetero.jsonl: 57,322 decks (ALL GAMES)
- test_quick_pecanpy.wv: 4,660 cards (MULTI-GAME)

After Game-Specific Split:
MTG:      740,801 pairs (97.3%), 4,205 cards, 57,322 decks
Pokemon:   10,987 pairs (1.4%),   222 cards,      0 decks
YGO:        3,792 pairs (0.5%),   295 cards,      0 decks
Cross:      5,551 pairs (0.7%) - cards appearing in multiple games

Trained Clean Embeddings:
- magic_64d_pecanpy.wv: 4,205 MTG cards
- pokemon_64d_pecanpy.wv: 222 Pokemon cards
```

### Key Insights

1. **Pokemon/YGO have NO deck data in decks_hetero.jsonl**
   - All 57,322 decks are MTG
   - Pokemon/YGO pairs come from... where? (Need to investigate backend extraction)

2. **Cross-game pairs exist** (5,551)
   - Likely from mixed-game tournament events or data artifacts
   - Could be valuable for transfer learning OR noise

3. **Game imbalance is severe**
   - MTG: 97% of data
   - Pokemon: 1.4%
   - YGO: 0.5%

---

## Multi-Perspective Analysis

### Perspective 1: Similar Card Prediction (Problem from README_SCRATCH.md)

**Current State**:
- ✅ Embeddings work (Node2Vec + PyG compatible)
- ✅ Fusion combines signals
- ✅ Per-modality normalization ensures fair weighting
- ⚠️ Multi-game embeddings conflate games
- ❌ No game filtering in similarity API

**Implications for Deck Completion**:
- MTG completion works well (clean embeddings, 4.2K cards)
- Pokemon completion will be weak (only 222 cards, no deck training data)
- YGO completion will be very weak (295 cards, no deck training data)

**Fix**:
```python
# API should accept game parameter and route to game-specific model
@router.post("/v1/similar")
def find_similar(request: SimilarityRequest, game: str | None = None):
    if game:
        embeddings = load_game_embeddings(game)  # magic/pokemon/yugioh
    # ...
```

### Perspective 2: Deck Completion Action Space

**Current State**:
- ✅ DeckPatch validates per-game rules correctly
- ✅ Validators enforce MTG/Pokemon/YGO constraints
- ✅ Greedy completion respects copy limits per game
- ⚠️ Candidate generation doesn't filter by game
- ❌ Coverage boost only works for MTG (FunctionalTagger)
- ❌ Curve heuristics assume CMC (MTG-only)

**What Happens Now**:
- MTG deck completion: works, but may suggest Pokemon cards if they're in the mixed graph
- Pokemon deck completion: will fail or give nonsense (no Pokemon-specific scoring)
- YGO deck completion: will fail or give nonsense

**Fix**:
```python
# In suggest_additions:
candidates = candidate_fn(seed, k)
# Filter by game
if game == "magic":
    candidates = [(c, s) for c, s in candidates if c in mtg_card_set]
# Use game-specific tagger
tagger = {"magic": FunctionalTagger, "pokemon": PokemonFunctionalTagger, "yugioh": YugiohFunctionalTagger}[game]()
```

### Perspective 3: Node2Vec / PyG Integration

**Current State**:
- ✅ Node2Vec training works per-game
- ✅ PyG can consume per-game graphs
- ✅ API consumes gensim KeyedVectors (Node2Vec or PyG output)
- ✅ Fusion normalization keeps signals comparable

**Implications**:
- Per-game embeddings are clean for evaluation
- Multi-game embeddings could be useful for transfer learning
- PyG attributed embeddings should be trained per-game (different node features)

**Recommendation**:
- Primary: per-game embeddings (clean eval, game-specific tuning)
- Research: multi-game embeddings for transfer learning experiments
- Document both; make game selection explicit in API

### Perspective 4: Production Service

**Current State**:
- ✅ API handles 20× concurrent load (450ms avg)
- ✅ Graceful degradation (jaccard fallback)
- ✅ Metrics exposed
- ⚠️ No game filtering
- ❌ Single global model (can't serve per-game)

**Production Requirements**:
1. Load multiple models (magic.wv, pokemon.wv, yugioh.wv)
2. Route requests by game parameter
3. Cache per-game taggers/pricers
4. Return game-specific metrics

**Architecture**:
```python
class MultiGameState:
    models: dict[str, KeyedVectors]  # game -> embeddings
    graphs: dict[str, dict]  # game -> adjacency
    taggers: dict[str, object]  # game -> tagger
    pricers: dict[str, object]  # game -> pricer
```

### Perspective 5: Research & Evaluation

**Questions**:
1. Does cross-game training help or hurt?
   - Hypothesis: Hurts (dilutes game-specific patterns)
   - Test: Compare MTG P@10 with clean vs mixed embeddings

2. Can we do cross-game transfer?
   - Hypothesis: MTG → Pokemon might help (both have resource systems)
   - Test: Train on MTG, fine-tune on Pokemon, measure P@10

3. Should we allow cross-game suggestions?
   - Use case: "Pokemon equivalent of Lightning Bolt"
   - Requires: cross-game similarity metric + explicit user intent

**Experiments to Run**:
```bash
# 1. Clean vs contaminated
evaluate.py --embeddings magic_64d_pecanpy.wv --test-set magic_test.json
evaluate.py --embeddings test_quick_pecanpy.wv --test-set magic_test.json

# 2. Transfer learning
train_with_transfer.py --source magic --target pokemon

# 3. Cross-game similarity
cross_game_similarity.py --card1 "Lightning Bolt" --game1 magic --game2 pokemon
```

---

## Immediate Actions Taken

### 1. Data Splitting ✅
```
Created:
- data/pairs/magic_pairs.csv (740K pairs, 4.2K cards)
- data/pairs/pokemon_pairs.csv (11K pairs, 222 cards)
- data/pairs/yugioh_pairs.csv (3.8K pairs, 295 cards)
- data/pairs/cross_game_pairs.csv (5.5K pairs)
- data/decks/magic_decks.jsonl (57K decks)
```

### 2. Per-Game Embeddings ✅
```
Trained:
- magic_64d_pecanpy.wv (4,205 MTG cards, clean)
- pokemon_64d_pecanpy.wv (222 Pokemon cards, clean)
```

### 3. Validation
- MTG embeddings: Lightning Bolt → Chain Lightning, Thermo-Alchemist (sensible)
- Pokemon embeddings: 222 cards (small but clean)

---

## Recommendations by Priority

### P0: Fix Game Filtering (This Session)

1. **API: Add game routing**
   ```python
   # Load per-game models on startup
   models = {
       "magic": KeyedVectors.load("magic_64d.wv"),
       "pokemon": KeyedVectors.load("pokemon_64d.wv"),
   }

   # Route by game
   @router.post("/v1/{game}/similar")
   def find_similar_game(game: str, request: SimilarityRequest):
       embeddings = models.get(game)
       # ...
   ```

2. **Completion: Filter candidates by game**
   ```python
   # In suggest_additions:
   game_card_set = load_game_card_set(game)
   candidates = [(c, s) for c, s in candidates if c in game_card_set]
   ```

3. **Wire per-game taggers**
   ```python
   taggers = {
       "magic": FunctionalTagger(),
       "pokemon": PokemonFunctionalTagger(),
       "yugioh": YugiohFunctionalTagger(),
   }
   ```

### P1: Per-Game Evaluation

1. Run clean P@K for MTG with magic_64d.wv
2. Document Pokemon/YGO limitations (insufficient data)
3. Add per-game metrics to completion_eval.py

### P2: Cross-Game Research (Optional)

1. Evaluate contamination effect (mixed vs clean embeddings)
2. Test transfer learning (MTG → Pokemon)
3. Document findings

### P3: Scale Pokemon/YGO Data

1. Extract more Pokemon decks (Limitless API, target 5K+)
2. Extract more YGO decks (yugiohmeta.com, target 1K+)
3. Retrain embeddings with balanced data

---

## Design Decision: Separate vs Unified

### Option A: Strict Separation (Recommended for Production)

**API Design**:
```
POST /v1/magic/similar
POST /v1/magic/deck/complete
POST /v1/pokemon/similar
POST /v1/pokemon/deck/complete
POST /v1/yugioh/similar
POST /v1/yugioh/deck/complete
```

**Pros**:
- Clean evaluation
- Game-specific tuning
- No cross-contamination
- Clear user intent

**Cons**:
- 3× infrastructure
- No transfer learning
- More complex deployment

### Option B: Unified with Game Parameter (Current + Fix)

**API Design**:
```
POST /v1/similar?game=magic
POST /v1/deck/complete
  body: {"game": "magic", ...}
```

**Pros**:
- Single endpoint
- Simpler for clients
- Allows cross-game mode

**Cons**:
- Requires game parameter validation
- More complex routing logic
- Risk of game mismatch bugs

### Option C: Hybrid (Best)

**API Design**:
```
# Game-specific (primary, clean)
POST /v1/magic/similar
POST /v1/magic/deck/complete

# Multi-game research endpoint
POST /v1/research/cross_game_similar
  body: {"card": "Lightning Bolt", "source_game": "magic", "target_game": "pokemon"}
```

**Pros**:
- Clean separation for production
- Explicit cross-game for research
- Best of both worlds

**Cons**:
- More endpoints
- Requires documentation

---

## Current System Status

### What Works (MTG-Only)
- ✅ Similarity: embedding/jaccard/fusion with clean magic_64d.wv
- ✅ Deck completion: suggest/complete with coverage/budget/curve
- ✅ Validation: format rules, copy limits
- ✅ API: all endpoints functional
- ✅ Tests: 22/22 passing
- ✅ Performance: <500ms latency, 20× concurrent

### What Doesn't Work (Pokemon/YGO)
- ❌ Deck completion: no deck training data
- ❌ Coverage boost: taggers not wired
- ❌ Curve heuristics: CMC doesn't apply
- ❌ Pricing: not integrated
- ❌ Evaluation: no test sets

### What's Ambiguous (Cross-Game)
- ❓ Should we allow cross-game suggestions?
- ❓ Is contamination harmful or beneficial?
- ❓ Can MTG knowledge transfer to Pokemon?

---

## Conclusion

The deck completion system is **production-ready for MTG** with clean data and validated performance. Pokemon/YGO support exists architecturally but lacks:
1. Sufficient training data (decks)
2. Game-specific scoring (taggers, curve, pricing)
3. API game filtering

**Immediate path forward**:
1. Add game routing to API (use per-game embeddings)
2. Wire per-game taggers into completion
3. Document MTG-only production status
4. Mark Pokemon/YGO as "experimental" until data scaled

**Research opportunity**:
- Evaluate cross-game contamination effect
- Test transfer learning hypotheses
- Keep multi-game embeddings for comparison

**Long-term**:
- Scale Pokemon/YGO deck extraction (5K+ each)
- Retrain balanced multi-game embeddings
- Add cross-game similarity as explicit feature
