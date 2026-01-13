# Test Set Expansion Plan

## Current Status

- **Magic**: 940 queries ✅ (exceeds 100+ target)
- **Pokemon**: 58 queries (needs 42+ more to reach 100)
- **Yugioh**: 58 queries (needs 42+ more to reach 100)
- **Riftbound**: 4 queries (needs 96+ more to reach 100)

## Target: 100+ queries per game

### Rationale
- Statistical confidence for evaluation metrics
- Better coverage of card types, archetypes, formats
- More robust performance measurement

## Expansion Strategy

### Pokemon (58 → 100+)
1. **Functional roles**: Add 20 queries covering:
   - Energy acceleration (e.g., "Double Colorless Energy")
   - Draw/search (e.g., "Professor's Research")
   - Disruption (e.g., "Boss's Orders")
   - Setup (e.g., "Nest Ball")

2. **Archetype staples**: Add 15 queries for popular archetypes:
   - Charizard ex variants
   - Lost Zone variants
   - VMAX variants

3. **Format-specific**: Add 7 queries for Standard vs Expanded differences

### Yugioh (58 → 100+)
1. **Functional roles**: Add 20 queries covering:
   - Hand traps (e.g., "Ash Blossom & Joyous Spring")
   - Board breakers (e.g., "Lightning Storm")
   - Consistency cards (e.g., "Pot of Prosperity")
   - Extenders (e.g., "Called by the Grave")

2. **Archetype staples**: Add 15 queries for popular archetypes:
   - Branded variants
   - Kashtira variants
   - Tearlaments variants

3. **Format-specific**: Add 7 queries for TCG vs OCG differences

### Riftbound (4 → 100+)
1. **Complete coverage needed**: This is a new game with limited data
2. **Strategy**:
   - Start with functional roles (30 queries)
   - Add archetype staples as they emerge (30 queries)
   - Include format-specific cards (20 queries)
   - Add power level variants (20 queries)

## Implementation

### Option 1: Manual Annotation
- Use existing annotation workflow
- Target: 2-3 hours per game
- Quality: High (human-validated)

### Option 2: LLM-Assisted Generation
- Use LLM to generate candidate queries
- Human review for quality
- Target: 1 hour per game
- Quality: Medium-High (LLM + human review)

### Option 3: Hybrid Approach
- LLM generates candidates
- Human annotates relevance labels
- Target: 1.5 hours per game
- Quality: High (human labels)

## Recommended: Hybrid Approach

1. Use LLM to generate 50+ candidate queries per game
2. Human review and select best 40-50 queries
3. Human annotate relevance labels (highly_relevant, relevant, etc.)
4. Merge into unified test sets

## Next Steps

1. Create expansion scripts using LLM generation
2. Review and curate generated queries
3. Annotate relevance labels
4. Merge into unified test sets
5. Re-run evaluations to verify improvements

## Files to Update

- `experiments/test_set_unified_pokemon.json`
- `experiments/test_set_unified_yugioh.json`
- `experiments/test_set_unified_riftbound.json`
- `scripts/unify_test_sets.py` (if exists)
