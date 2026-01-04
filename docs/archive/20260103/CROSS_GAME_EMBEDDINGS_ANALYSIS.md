# Cross-Game Embeddings Analysis

## Research Question
Does cross-game training (Magic + Pokemon + Yu-Gi-Oh) make sense for our use cases?

## Our Use Cases
1. **Card Similarity Search**: Find similar cards within a game
2. **Deck Completion**: Suggest cards to add to a partial deck (game-specific)
3. **Card Substitution**: Find replacement cards within same game/format/archetype
4. **Contextual Discovery**: Find synergies, alternatives, upgrades (game-specific)

**Key Finding**: ALL tasks are within-game. We never compare cards across games.

## Research Findings

### When Cross-Game Makes Sense
- Games share structural similarities (e.g., team-based multiplayer games)
- Transfer learning beneficial (limited data in target game)
- Task-agnostic embeddings needed
- High structural overlap in graphs

### When Cross-Game Doesn't Make Sense
- Games differ fundamentally (different rules, mechanics)
- Tasks are domain-specific
- Evaluation is per-domain
- High computational cost, low benefit

## Our Situation

### Game Differences
- **Magic**: 5 colors, mana system, 60-card decks, stack mechanics
- **Pokemon**: Energy system, evolution, 60-card decks, HP-based
- **Yu-Gi-Oh**: No mana, special summoning, 40-60 cards, turn-based resources

These are **fundamentally different** rule systems, not minor variations.

### Our Tasks
- All within-game (no cross-game queries)
- Game-specific contexts (format, archetype, meta)
- Game-specific evaluation (separate test sets per game)

### Data Availability
- Magic: Large dataset (91% vocabulary coverage)
- Pokemon: Medium dataset (50% coverage)
- Yu-Gi-Oh: Smaller dataset (27.6% coverage)

## Recommendation

### Option 1: Game-Specific Embeddings (RECOMMENDED)
- Train separate embeddings per game
- Better for game-specific tasks
- Simpler, more interpretable
- No cross-game noise
- Each game optimized for its own mechanics

### Option 2: Multi-Game with NO Cross-Game Walks
- Train on all games but keep walks within-game (cross-game prob = 0.0)
- Shared embedding space for vocabulary
- But separate game-specific training
- May help with vocabulary coverage

### Option 3: Multi-Game with Cross-Game (CURRENT)
- Cross-game prob = 0.1 (10% cross-game transitions)
- May learn some shared patterns
- But risks diluting game-specific signals
- Unclear benefit for our use cases

## Conclusion

**Cross-game walks (prob > 0) likely don't help** for our use cases because:
1. All tasks are within-game
2. Games have fundamentally different mechanics
3. Cross-game training may add noise to game-specific signals
4. Research suggests domain-specific tasks benefit from domain-specific training

## Next Steps
1. Let current multi-game training finish (for comparison)
2. Train game-specific embeddings for each game
3. Evaluate: multi-game vs game-specific on game-specific tasks
4. Choose based on results

## References
- Research on Magic: The Gathering transfer learning (within-game generalization)
- Graph embedding transfer learning literature
- Our evaluation framework (all game-specific)
