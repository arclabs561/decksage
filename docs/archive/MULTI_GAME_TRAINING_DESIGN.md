# Multi-Game Training Design

## Overview

Training embeddings on all games simultaneously offers several benefits:
- **Larger training corpus**: More data = better embeddings
- **Cross-game transfer learning**: Similar patterns across games (removal spells, card draw, etc.)
- **Unified embedding space**: Compare cards across games (useful for design analysis)
- **Better generalization**: Models learn universal card game patterns

## Current Architecture

The codebase already supports multi-game:
- **Universal types**: `Collection`, `Partition`, `CardDesc` work across all games
- **Game-specific cards**: Each game has its own `Card` struct with game-specific fields
- **Data organization**: Collections stored in `games/{game}/` directories

## Required Dataset Representations

### 1. Game-Aware Graph Export

**Current**: `export-graph` only exports MTG pairs
**Needed**: `export-multi-game-graph` that:
- Extracts pairs from all games (MTG, YGO, PKM)
- Includes game type as edge/node attribute
- Preserves deck context (archetype, format, source)

**Format**:
```csv
NAME_1,NAME_2,GAME_1,GAME_2,COUNT,DECK_ID,SOURCE
Lightning Bolt,Counterspell,MTG,MTG,15,deck_123,mtgtop8
Dark Magician,Blue-Eyes White Dragon,YGO,YGO,8,deck_456,ygoprodeck
```

### 2. Game Metadata

**Needed**: Explicit game type for each card/deck
- **Current**: Inferred from collection type or source
- **Better**: Explicit `game` field in collections
- **Fallback**: Heuristic based on source/type

### 3. Unified Card Attributes

**Challenge**: Different games have different attributes
- **MTG**: type_line, mana_cost, colors, cmc
- **YGO**: type, attribute, level, atk, def
- **PKM**: supertype, types, hp, attacks

**Solution**: Normalize to common attributes:
- `card_type`: Creature/Monster/Pokemon, Spell/Instant/Sorcery, etc.
- `cost`: mana_cost, level, energy_cost (normalized)
- `power`: power, atk, damage (normalized)
- `game`: MTG, YGO, PKM

## Training Approaches

### Option 1: Unified Embeddings (Recommended)

**Approach**: Single embedding space for all games
- **Pros**: Cross-game similarity, larger training data, unified space
- **Cons**: May mix game-specific patterns
- **Use case**: General card similarity, cross-game analysis

**Implementation**:
- Game-aware random walks (configurable cross-game probability)
- Game type as node feature
- Single Word2Vec model

### Option 2: Game-Specific Embeddings

**Approach**: Separate embeddings per game
- **Pros**: Game-specific patterns preserved, no contamination
- **Cons**: No cross-game similarity, smaller training data per game
- **Use case**: Game-specific recommendations

**Implementation**:
- Filter graph by game before training
- Train separate models
- Can combine via fusion later

### Option 3: Hybrid (Both)

**Approach**: Train both unified and game-specific
- **Pros**: Best of both worlds
- **Cons**: More compute, more storage
- **Use case**: Flexible similarity (can use either)

## Random Walk Strategies

### 1. Game-Constrained Walks
- Stay within game (cross_game_prob = 0.0)
- Preserves game-specific patterns
- Good for game-specific embeddings

### 2. Cross-Game Walks
- Allow transitions between games (cross_game_prob > 0.0)
- Learns cross-game patterns
- Good for unified embeddings

### 3. Weighted Cross-Game
- Prefer same-game transitions but allow cross-game
- Balance between specificity and generalization
- Recommended: cross_game_prob = 0.1-0.2

## Evaluation Considerations

### Game-Aware Evaluation

**Critical**: Don't evaluate MTG queries against YGO cards
- Filter candidates by game type
- Separate metrics per game
- Cross-game metrics (optional, for design analysis)

### Test Set Structure

```json
{
  "queries": {
    "Lightning Bolt": {
      "game": "MTG",
      "highly_relevant": ["Chain Lightning", "Lava Spike"],
      ...
    },
    "Dark Magician": {
      "game": "YGO",
      "highly_relevant": ["Blue-Eyes White Dragon", ...],
      ...
    }
  }
}
```

## Implementation Plan

### Phase 1: Data Export
1. ✅ Create `export-multi-game-graph` command
2. Export pairs with game context
3. Include deck metadata (archetype, format, source)

### Phase 2: Training Script
1. ✅ Create `train_multi_game_embeddings.py`
2. Support unified and game-specific modes
3. Configurable cross-game probability

### Phase 3: Evaluation
1. Game-aware evaluation script
2. Separate metrics per game
3. Cross-game analysis (optional)

### Phase 4: Integration
1. Update API to handle multi-game queries
2. Game-aware similarity search
3. Cross-game similarity (optional feature)

## Benefits

### For Similarity Search
- **Larger corpus**: More cards = better coverage
- **Better embeddings**: More training data = higher quality
- **Cross-game patterns**: Learn universal card game principles

### For Research
- **Design analysis**: Compare cards across games
- **Pattern discovery**: Find similar mechanics across games
- **Transfer learning**: Apply patterns from one game to another

## Challenges

### 1. Name Collisions
**Problem**: Same card name in different games
**Solution**: Prefix with game type: `MTG:Lightning Bolt` vs `YGO:Lightning Bolt`

### 2. Attribute Mismatch
**Problem**: Different games have different attributes
**Solution**: Normalize to common attributes, use game-specific features

### 3. Evaluation Complexity
**Problem**: How to evaluate cross-game similarity?
**Solution**: Separate game-specific metrics, optional cross-game analysis

## Next Steps

1. **Export multi-game graph**: Run `export-multi-game-graph` on all data
2. **Train unified embeddings**: Use `train_multi_game_embeddings.py` with cross-game prob = 0.1
3. **Evaluate**: Game-aware evaluation on test sets
4. **Compare**: Unified vs game-specific performance
5. **Iterate**: Adjust cross-game probability, add game features

## Files Created

- `src/backend/cmd/export-multi-game-graph/main.go` - Multi-game graph export
- `src/ml/scripts/train_multi_game_embeddings.py` - Multi-game training script
- `MULTI_GAME_TRAINING_DESIGN.md` - This document

