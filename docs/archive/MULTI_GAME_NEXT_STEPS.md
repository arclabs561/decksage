# Multi-Game Training: Next Steps

## Summary

You asked: "what if we trained on all games at once? haa but we do need more dataset representations"

**Answer**: Great idea! Multi-game training offers:
- **Larger training corpus** (more data = better embeddings)
- **Cross-game transfer learning** (similar patterns across games)
- **Unified embedding space** (compare cards across games)

## What I Created

### 1. Multi-Game Graph Export (`export-multi-game-graph`)
- Exports pairs from all games (MTG, YGO, PKM)
- Includes game type as edge attribute
- Preserves deck context (archetype, format, source)

### 2. Multi-Game Training Script (`train_multi_game_embeddings.py`)
- **Unified mode**: Single embedding space for all games
- **Game-specific mode**: Separate embeddings per game
- **Hybrid mode**: Both unified and game-specific
- **Configurable cross-game probability**: Control how much games mix

### 3. Design Document (`MULTI_GAME_TRAINING_DESIGN.md`)
- Complete design rationale
- Training approaches (unified vs game-specific)
- Evaluation considerations
- Implementation plan

## What We Need (Dataset Representations)

### Current State
- ✅ Multi-game architecture exists (MTG, YGO, PKM)
- ✅ Universal collection types
- ✅ Game-specific card structures
- ❌ No unified graph export with game context
- ❌ No game metadata in pairs CSV

### Needed Representations

1. **Game-Aware Pairs CSV**
   - Format: `NAME_1,NAME_2,GAME_1,GAME_2,COUNT,DECK_ID,SOURCE`
   - Includes game type for each card
   - Preserves deck context

2. **Game Metadata**
   - Explicit game type per collection
   - Currently inferred from source/type (heuristic)
   - Better: explicit `game` field

3. **Unified Card Attributes**
   - Normalize across games:
     - `card_type`: Creature/Monster/Pokemon, Spell/Instant, etc.
     - `cost`: mana_cost, level, energy_cost (normalized)
     - `power`: power, atk, damage (normalized)
     - `game`: MTG, YGO, PKM

## How to Use

### Step 1: Export Multi-Game Graph
```bash
cd src/backend/cmd/export-multi-game-graph
go run main.go ../../data-full data/processed/pairs_multi_game.csv
```

### Step 2: Train Unified Embeddings
```bash
uv run --script src/ml/scripts/train_multi_game_embeddings.py \
  --mtg-pairs data/processed/pairs_large.csv \
  --ygo-pairs data/processed/pairs_ygo.csv \
  --pkm-pairs data/processed/pairs_pkm.csv \
  --output data/embeddings/multi_game_unified.wv \
  --mode unified \
  --cross-game-prob 0.1 \
  --dim 128
```

### Step 3: Train Game-Specific Embeddings (Optional)
```bash
uv run --script src/ml/scripts/train_multi_game_embeddings.py \
  --mtg-pairs data/processed/pairs_large.csv \
  --ygo-pairs data/processed/pairs_ygo.csv \
  --pkm-pairs data/processed/pairs_pkm.csv \
  --output data/embeddings/multi_game.wv \
  --mode game-specific \
  --dim 128
```

## Benefits

### For Similarity Search
- **Larger corpus**: More cards = better coverage
- **Better embeddings**: More training data = higher quality
- **Cross-game patterns**: Learn universal card game principles

### For Research
- **Design analysis**: Compare cards across games
- **Pattern discovery**: Find similar mechanics across games
- **Transfer learning**: Apply patterns from one game to another

## Challenges & Solutions

### 1. Name Collisions
**Problem**: Same card name in different games  
**Solution**: Prefix with game type: `MTG:Lightning Bolt` vs `YGO:Lightning Bolt`

### 2. Attribute Mismatch
**Problem**: Different games have different attributes  
**Solution**: Normalize to common attributes, use game-specific features

### 3. Evaluation Complexity
**Problem**: How to evaluate cross-game similarity?  
**Solution**: Separate game-specific metrics, optional cross-game analysis

## Next Actions

1. **Test export**: Run `export-multi-game-graph` on your data
2. **Check data**: Verify game distribution and pair counts
3. **Train unified**: Start with cross-game prob = 0.1
4. **Evaluate**: Compare unified vs game-specific performance
5. **Iterate**: Adjust cross-game probability based on results

## Files Created

- `src/backend/cmd/export-multi-game-graph/main.go` - Multi-game graph export
- `src/ml/scripts/train_multi_game_embeddings.py` - Multi-game training
- `MULTI_GAME_TRAINING_DESIGN.md` - Complete design document
- `MULTI_GAME_NEXT_STEPS.md` - This summary

**Ready to train on all games!** 🎮

