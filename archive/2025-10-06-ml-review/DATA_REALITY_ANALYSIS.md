# Data Reality Analysis - Multi-Perspective Introspection

**Date**: October 5, 2025  
**Context**: Post deck-completion implementation; preparing for multi-game policy optimization

---

## Reality Check: What We Actually Have

### Data Files (Actual Counts)

```
MTG:     351,689 files (cards + decks from scryfall/mtgtop8/goldfish/deckbox)
Pokemon:   1,208 files (limitless-web tournament decks)
YGO:          20 files (ygoprodeck-tournament sample)

Decks:    57,322 lines in decks_hetero.jsonl (MIXED GAMES)
Pairs:   761,132 lines in pairs.csv (MIXED GAMES)
Graph:     6,623 unique cards, 1.4M edges (MULTI-GAME)
```

### Critical Insight: Multi-Game Conflation

**pairs.csv contains ALL games mixed**:
- Sample: "Eri" (Pokemon), "The One Ring" (MTG), "Genesect" (Pokemon), "Rift Bolt" (MTG)
- This is NOT a bug; it's multi-game co-occurrence
- Implication: Node2Vec embeddings span games; "similar" cards may cross games

**Problem 1: Cross-Game Contamination**
- Asking for "Lightning Bolt" substitutes might return Pokemon "Lightning Energy"
- Deck completion for MTG might suggest Pokemon cards if they co-occur in the mixed graph
- Functional tags are game-specific; coverage boost won't work cross-game

**Problem 2: Game Imbalance**
- MTG: 351K files (99.6%)
- Pokemon: 1.2K files (0.3%)
- YGO: 20 files (0.006%)
- Node2Vec will be MTG-dominated; Pokemon/YGO embeddings undertrained

---

## Multi-Perspective Analysis

### Perspective 1: Data Quality Engineer

**Strengths**:
- ✅ 57K decks with tournament metadata
- ✅ Unified schema (Collection/Partition/CardDesc)
- ✅ Validators enforce format rules per game

**Gaps**:
- ❌ No game-specific pairs.csv (mtg_pairs.csv, pokemon_pairs.csv, yugioh_pairs.csv)
- ❌ No game-specific embeddings (mtg_64d.wv, pokemon_64d.wv, yugioh_64d.wv)
- ❌ No game labels in pairs.csv (can't filter by game without external lookup)
- ❌ decks_hetero.jsonl has empty format/archetype fields (per DATA_VALIDATION.md)

**Action**: Split pairs.csv and train per-game embeddings

### Perspective 2: ML Pipeline Designer

**Strengths**:
- ✅ Node2Vec training works (card_similarity_pecan.py)
- ✅ Evaluation framework (evaluate.py, P@K/MRR)
- ✅ Fusion combines signals cleanly

**Gaps**:
- ❌ Test sets are game-specific but embeddings are multi-game
- ❌ No cross-game evaluation (does Pokemon P@10 suffer from MTG contamination?)
- ❌ Functional taggers exist per game but aren't wired into fusion for Pokemon/YGO
- ❌ No per-game fusion weight tuning

**Action**: Train per-game embeddings; add game parameter to API; tune fusion per game

### Perspective 3: Deck Completion System Designer

**Strengths**:
- ✅ DeckPatch validates per-game rules
- ✅ Completion respects copy limits per game
- ✅ API accepts game parameter

**Gaps**:
- ❌ Candidate generation doesn't filter by game; will suggest cross-game cards
- ❌ Coverage boost uses MTG FunctionalTagger only; Pokemon/YGO get no boost
- ❌ Curve heuristics assume MTG CMC; Pokemon energy/YGO levels need different logic
- ❌ Budget uses MTG pricing only; Pokemon/YGO pricing not integrated

**Action**: Add game filtering to candidate generation; wire per-game taggers/pricing

### Perspective 4: Multi-Game Researcher

**Strengths**:
- ✅ Cross-game transfer learning possible (if intentional)
- ✅ Unified ontology enables comparison

**Gaps**:
- ❌ No explicit cross-game similarity metric
- ❌ No game-specific evaluation
- ❌ Unclear if cross-game contamination helps or hurts

**Questions**:
- Should "Lightning Bolt" (MTG) be similar to "Lightning Energy" (Pokemon)?
- Can Pokemon deck completion benefit from MTG embeddings (transfer learning)?
- Or should we strictly partition by game?

**Action**: Decide on cross-game policy; provide both options

### Perspective 5: Production Service Operator

**Strengths**:
- ✅ API returns metrics (timings, counts)
- ✅ Graceful degradation (jaccard fallback when no embeddings)
- ✅ Concurrent load tested (20× threads, 450ms avg)

**Gaps**:
- ❌ No game filtering in similarity endpoints
- ❌ FunctionalTagger spams build logs on every request
- ❌ No caching of tagger/price manager across requests
- ❌ No rate limiting or request quotas

**Action**: Add game filter param; prebuild tagger; add caching

---

## Proposed Dataset Organization

### Current (Mixed)
```
pairs.csv                    # ALL GAMES MIXED
decks_hetero.jsonl          # ALL GAMES MIXED
test_quick_pecanpy.wv       # MULTI-GAME embeddings
```

### Proposed (Per-Game + Multi-Game)

```
data/
├── pairs/
│   ├── magic_pairs.csv          # MTG-only co-occurrence
│   ├── pokemon_pairs.csv        # Pokemon-only
│   ├── yugioh_pairs.csv         # YGO-only
│   └── multi_game_pairs.csv     # Cross-game (intentional)
│
├── decks/
│   ├── magic_decks.jsonl        # MTG tournament decks
│   ├── pokemon_decks.jsonl      # Pokemon tournament decks
│   ├── yugioh_decks.jsonl       # YGO tournament decks
│   └── multi_game_decks.jsonl   # Mixed (for cross-game research)
│
├── embeddings/
│   ├── magic_64d_node2vec.wv    # MTG-only embeddings
│   ├── pokemon_64d_node2vec.wv  # Pokemon-only
│   ├── yugioh_64d_node2vec.wv   # YGO-only
│   ├── multi_game_64d.wv        # Cross-game (transfer learning)
│   └── magic_128d_pyg.wv        # PyG attributed (MTG)
│
├── attributes/
│   ├── magic_attrs.csv          # cmc, type, color, keywords
│   ├── pokemon_attrs.csv        # hp, type, energy_cost
│   └── yugioh_attrs.csv         # atk, def, level, type
│
└── test_sets/
    ├── magic_test_canonical.json
    ├── pokemon_test_canonical.json
    └── yugioh_test_canonical.json
```

### Benefits
1. **Clean evaluation**: per-game P@K without contamination
2. **Explicit cross-game**: multi_game_* files for transfer learning research
3. **Scalable**: add games without polluting existing data
4. **Debuggable**: know which game each file represents

---

## Multi-Game Deck Completion Considerations

### Game-Specific Constraints

| Constraint | MTG | Pokemon | YGO |
|------------|-----|---------|-----|
| Main size | 60+ | 60 exact | 40-60 |
| Copy limit | 4 (1 for singleton) | 4 (∞ for basic Energy) | 3 |
| Sideboard | 0-15 | None | 0-15 (Side Deck) |
| Extra deck | None | None | 0-15 |
| Partitions | Main, Sideboard | Main Deck | Main/Extra/Side |

### Game-Specific Scoring

**MTG**:
- CMC curve (1-7+)
- Color pips (WUBRG)
- Land count (17-27 typical)
- Tags: removal, ramp, draw, counterspell

**Pokemon**:
- Energy count (10-15 typical)
- Trainer/Pokemon/Energy ratio
- Evolution chains
- Tags: draw_support, energy_acceleration, heavy_hitter

**YGO**:
- Monster/Spell/Trap ratio
- Hand trap count
- Starter/extender balance
- Tags: hand_trap, board_breaker, negate

### Current Implementation Status

| Feature | MTG | Pokemon | YGO |
|---------|-----|---------|-----|
| Validators | ✅ | ✅ | ✅ |
| Functional tags | ✅ | ✅ | ✅ |
| Pricing | ✅ | ⚠️ (stub) | ⚠️ (stub) |
| Curve heuristics | ✅ (CMC) | ❌ | ❌ |
| Completion tested | ✅ | ❌ | ❌ |

---

## Recommendations

### Immediate (This Session)

1. **Split pairs.csv by game**
   ```bash
   # Filter by card name lookup against game-specific card databases
   python split_pairs_by_game.py \
     --input src/backend/pairs.csv \
     --output data/pairs/
   ```

2. **Train per-game embeddings**
   ```bash
   uv run python card_similarity_pecan.py --input data/pairs/magic_pairs.csv --output magic_64d
   uv run python card_similarity_pecan.py --input data/pairs/pokemon_pairs.csv --output pokemon_64d
   uv run python card_similarity_pecan.py --input data/pairs/yugioh_pairs.csv --output yugioh_64d
   ```

3. **Add game filter to API**
   ```python
   # In suggest_actions/complete:
   if req.game_filter:
       # Filter candidates by game before returning
   ```

4. **Wire per-game taggers into completion**
   ```python
   # In suggest_actions:
   if game == "pokemon":
       tagger = PokemonFunctionalTagger()
   elif game == "yugioh":
       tagger = YugiohFunctionalTagger()
   ```

### Short-Term (Next Week)

1. Generate attributes CSVs from Scryfall/PokemonTCG/YGOPRODeck APIs
2. Integrate Pokemon/YGO pricing (RapidAPI or YGOPRODeck)
3. Add per-game curve heuristics (energy count for Pokemon, monster ratio for YGO)
4. Evaluate per-game P@K with clean test sets

### Medium-Term (Next Month)

1. Cross-game transfer learning experiments (train on MTG, test on Pokemon)
2. Multi-game fusion weights (does Pokemon benefit from MTG functional tags?)
3. Supervised policy training on masked decks per game
4. Frontend deck builder with game selector

---

## Critical Issues Found

### Issue 1: Pairs.csv is Multi-Game Without Labels
**Impact**: High  
**Severity**: Critical for evaluation  
**Fix**: Split by game OR add game column

### Issue 2: Embeddings Trained on Mixed Data
**Impact**: High  
**Severity**: Evaluation metrics are contaminated  
**Fix**: Retrain per-game; keep multi-game as separate experiment

### Issue 3: Completion Only Works for MTG
**Impact**: Medium  
**Severity**: Pokemon/YGO completion will fail or give bad results  
**Fix**: Wire per-game taggers, pricing, curve heuristics

### Issue 4: No Game-Specific Evaluation
**Impact**: High  
**Severity**: Can't measure per-game quality  
**Fix**: Split test sets, run per-game P@K

---

## Philosophical Considerations

### Should Games Be Separate or Unified?

**Separate (Recommended)**:
- ✅ Clean evaluation per game
- ✅ Game-specific tuning (fusion weights, curve targets)
- ✅ Respects game mechanics differences
- ❌ Loses potential transfer learning
- ❌ More infrastructure (3× embeddings, 3× APIs)

**Unified (Current State)**:
- ✅ Simpler infrastructure
- ✅ Potential transfer learning (if Pokemon benefits from MTG patterns)
- ❌ Contaminated evaluation
- ❌ Game-specific features don't work (curve, pricing)
- ❌ Imbalanced training (99% MTG)

**Hybrid (Best)**:
- Train per-game embeddings as primary
- Keep multi-game embeddings for transfer learning research
- API accepts game parameter and routes to appropriate model
- Evaluation strictly per-game
- Document cross-game experiments separately

---

## Next Actions (Prioritized)

### P0: Data Hygiene
1. Split pairs.csv → magic_pairs.csv, pokemon_pairs.csv, yugioh_pairs.csv
2. Train per-game Node2Vec embeddings
3. Add game filter to API candidate generation

### P1: Multi-Game Completion
1. Wire Pokemon/YGO taggers into suggest/complete
2. Add per-game curve heuristics (energy for Pokemon, monster ratio for YGO)
3. Integrate Pokemon/YGO pricing

### P2: Evaluation
1. Run per-game P@K with clean embeddings
2. Document cross-game contamination effect
3. Add game-specific metrics to completion_eval.py

### P3: Documentation
1. Update README with per-game quick start
2. Document multi-game vs single-game trade-offs
3. Add game-specific completion examples

---

## Conclusion

The deck completion system is **architecturally sound** but **trained on contaminated data**. The multi-game mixing is not inherently wrong (could be intentional for transfer learning), but it's **undocumented and unevaluated**.

**Immediate fix**: Split data by game, retrain embeddings, add game filtering to API.  
**Research opportunity**: Evaluate if cross-game embeddings help (e.g., does Pokemon completion improve with MTG knowledge?).  
**Production path**: Per-game models with optional cross-game mode.
