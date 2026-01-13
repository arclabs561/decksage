# Game-Specific Context Injection

## Overview

The annotation system now uses **game-specific context injection** instead of unioned prompts. This prevents cross-contamination (e.g., Magic-specific advice affecting Pokemon annotations).

## Implementation

### 1. Game-Specific Prompts

Each game has tailored context in `get_similarity_prompt()`:

- **Magic**: Function-based scoring rules (removal, draw, counter)
- **Pokemon**: Type and evolution line scoring
- **Yu-Gi-Oh**: Archetype and type scoring

**Location**: `src/ml/annotation/llm_annotator.py:217-249`

### 2. Game-Specific Meta-Judge Feedback

Meta-judge feedback is stored **per-game**, not unioned:

```python
# Game-specific storage
annotator.meta_judge_feedback_by_game = {
    "magic": {"critical": [...], "important": [...], "suggestions": [...]},
    "pokemon": {"critical": [...], "important": [...], "suggestions": [...]},
    "yugioh": {"critical": [...], "important": [...], "suggestions": [...]},
}
```

**Benefits**:
- Magic feedback only affects Magic annotations
- Pokemon feedback only affects Pokemon annotations
- No cross-contamination between games

**Location**: `src/ml/annotation/meta_judge.py:402-519`

### 3. Game-Specific Meta-Judge Evaluation

Meta-judge now receives game-specific guidance when evaluating:

- **Magic**: Focus on function-based scoring, avoid low clustering
- **Pokemon**: Focus on type and evolution relationships
- **Yu-Gi-Oh**: Focus on archetype and type relationships

**Location**: `src/ml/annotation/meta_judge.py:294-390`

### 4. Game-Specific Prompt Injection

When injecting feedback into prompts, the system:
1. Checks for game-specific feedback first
2. Only includes feedback tagged for the current game
3. Falls back to global feedback if no game-specific feedback exists

**Location**: `src/ml/annotation/llm_annotator.py:812-840`

## Game-Specific Rules

### Magic: The Gathering
- Same function (removal, draw, counter) → score >= 0.4
- Same function + similar attributes → score >= 0.5-0.7
- Examples: Lightning Bolt vs Shock → 0.7, Path vs Swords → 0.8

### Pokémon TCG
- Same type (Fire, Water, etc.) → score >= 0.4
- Same evolution line → score >= 0.5-0.7
- Same function → score >= 0.4-0.6
- Examples: Pikachu vs Raichu → 0.7, Charizard vs Blastoise → 0.3

### Yu-Gi-Oh!
- Same archetype → score >= 0.5-0.7
- Same type (Dragon, Warrior, etc.) → score >= 0.4-0.6
- Same function → score >= 0.4-0.6
- Examples: Blue-Eyes White Dragon vs Blue-Eyes Alternative → 0.8

## Validation

Run validation to ensure game-specific prompts work:

```bash
python3 -c "
from src.ml.annotation.llm_annotator import get_similarity_prompt
for game in ['magic', 'pokemon', 'yugioh']:
    prompt = get_similarity_prompt(game)
    assert f'{game.upper()}-SPECIFIC' in prompt or 'SPECIFIC' in prompt
    print(f'✓ {game} has game-specific context')
"
```

## Benefits

1. **No Cross-Contamination**: Magic advice doesn't affect Pokemon
2. **Tailored Guidance**: Each game gets relevant scoring rules
3. **Better Quality**: Game-specific feedback improves annotations
4. **Easier Debugging**: Can track feedback per-game

## Future Improvements

- Add game-specific examples to prompts
- Track feedback effectiveness per-game
- Add game-specific validation rules
- Create game-specific meta-judge prompts
