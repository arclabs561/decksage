# Deck Modification Implementation Plan

**Date**: 2025-01-27  
**Status**: Ready to implement

---

## Quick Start: What to Build First

### Priority 1: Enhanced Add Suggestions (2-3 days)

**Goal**: Make `/deck/suggest_actions` smarter with:
- Role-aware filtering
- Archetype context
- Better explanations

**Changes to `src/ml/deck_building/deck_completion.py`**:

1. **Add role gap detection**:
```python
def _detect_role_gaps(deck: dict, tag_set_fn) -> dict[str, int]:
    """Count cards by functional role."""
    role_counts = {}
    for card, count in deck.get("main", {}).items():
        tags = tag_set_fn(card) if tag_set_fn else set()
        for role in ["removal", "threat", "card_draw", "ramp"]:
            if role in tags:
                role_counts[role] = role_counts.get(role, 0) + count
    return role_counts
```

2. **Enhance `suggest_additions` with role awareness**:
```python
def suggest_additions(
    ...,
    role_aware: bool = True,
    archetype: Optional[str] = None,
    format: Optional[str] = None,
) -> list[tuple[str, float]]:
    # Detect role gaps
    if role_aware and tag_set_fn:
        gaps = _detect_role_gaps(deck, tag_set_fn)
        # Prioritize suggestions that fill gaps
    
    # Filter by archetype if provided
    if archetype:
        staples = _get_archetype_staples(archetype, format)
        # Boost staple scores
    
    # Existing similarity logic...
```

3. **Add explanation generation**:
```python
def _explain_suggestion(
    card: str,
    reason: str,
    context: dict,
) -> str:
    """Generate human-readable explanation."""
    if reason == "archetype_staple":
        rate = context.get("inclusion_rate", 0)
        return f"Archetype staple - appears in {rate:.0f}% of {context['archetype']} decks"
    elif reason == "role_gap":
        role = context.get("role")
        return f"Fills {role} gap - deck currently has {context['current_count']} {role} cards"
    # ...
```

---

### Priority 2: Remove/Replace Suggestions (2-3 days)

**Goal**: Help users identify weak/redundant cards

**New function in `deck_completion.py`**:
```python
def suggest_removals(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    fusion: WeightedLateFusion,
    archetype: Optional[str] = None,
    preserve_roles: bool = True,
) -> list[tuple[str, float, str]]:  # (card, score, reason)
    """
    Suggest cards to remove.
    
    Returns list of (card, removal_score, reason) tuples.
    """
    removals = []
    
    # 1. Find cards with low archetype match
    if archetype:
        staples = _get_archetype_staples(archetype)
        staple_set = {card for card, _ in staples}
        for card in deck.get("main", {}):
            if card not in staple_set:
                # Check how similar to archetype
                similarity = _archetype_similarity(card, archetype, fusion)
                if similarity < 0.3:
                    removals.append((card, 1.0 - similarity, "low_archetype_match"))
    
    # 2. Find redundant cards (multiple filling same role)
    if preserve_roles and tag_set_fn:
        role_cards = defaultdict(list)
        for card in deck.get("main", {}):
            tags = tag_set_fn(card)
            for role in ["removal", "threat", "card_draw"]:
                if role in tags:
                    role_cards[role].append(card)
        
        # If a role has too many cards, suggest removing weakest
        for role, cards in role_cards.items():
            if len(cards) > 8:  # Too many removal spells
                # Score by archetype match, suggest removing lowest
                scored = [(c, _archetype_similarity(c, archetype, fusion)) for c in cards]
                scored.sort(key=lambda x: x[1])
                for card, score in scored[:len(cards) - 6]:  # Keep top 6
                    removals.append((card, 0.7, f"redundant_{role}"))
    
    return sorted(removals, key=lambda x: x[1], reverse=True)
```

---

### Priority 3: Contextual Card Discovery (2 days)

**Goal**: "What works with this card?"

**New endpoint in `api.py`**:
```python
@router.get("/cards/{card}/contextual")
def get_contextual_suggestions(
    card: str,
    game: str,
    format: Optional[str] = None,
    archetype: Optional[str] = None,
):
    """
    Get contextual suggestions for a card:
    - Synergies (cards that work well together)
    - Alternatives (functional equivalents)
    - Upgrades (better versions)
    - Downgrades (budget alternatives)
    """
    state = get_state()
    fusion = _make_fusion(state)
    
    # Synergies: high co-occurrence in same decks
    synergies = _find_synergies(card, fusion, format, archetype)
    
    # Alternatives: functional similarity
    alternatives = _find_alternatives(card, fusion, tag_set_fn)
    
    # Upgrades/downgrades: price + power analysis
    upgrades = _find_upgrades(card, price_fn, fusion)
    downgrades = _find_downgrades(card, price_fn, fusion)
    
    return {
        "synergies": synergies,
        "alternatives": alternatives,
        "upgrades": upgrades,
        "downgrades": downgrades,
    }
```

---

## Data Requirements

### Need to Compute/Store

1. **Archetype Staples**:
   - File: `experiments/signals/archetype_staples.json`
   - Format: `{archetype: {card: inclusion_rate}}`
   - Already computed? Check `src/ml/scripts/compute_and_cache_signals.py`

2. **Format-Specific Co-occurrence**:
   - File: `experiments/signals/format_cooccurrence.json`
   - Format: `{format: {card1: {card2: cooccurrence_rate}}}`
   - Already computed? Check signals directory

3. **Role Coverage Templates**:
   - File: `data/archetype_templates.json` (new)
   - Format: `{archetype: {role: recommended_count}}`
   - Example: `{"Burn": {"removal": 12, "threats": 16, "card_draw": 4}}`

---

## Integration Points

### Existing Code to Enhance

1. **`src/ml/deck_building/deck_completion.py`**:
   - `suggest_additions` - add role awareness, archetype filtering
   - Add `suggest_removals` function
   - Add `suggest_replacements` function

2. **`src/ml/api/api.py`**:
   - Enhance `/deck/suggest_actions` with new parameters
   - Add `/deck/refine` endpoint
   - Add `/cards/{card}/contextual` endpoint

3. **`src/ml/similarity/fusion.py`**:
   - Already has archetype/format signals
   - Use for contextual discovery

### New Files to Create

1. **`src/ml/deck_building/role_analysis.py`**:
   - Role gap detection
   - Role coverage analysis
   - Role-based filtering

2. **`src/ml/deck_building/archetype_matching.py`**:
   - Archetype similarity scoring
   - Staple lookup
   - Template matching

3. **`src/ml/deck_building/explanation_generator.py`**:
   - Template-based explanations
   - Statistical backing
   - Human-readable reasons

---

## Testing Strategy

### Unit Tests

1. **Role gap detection**:
   - Deck with no removal → detects gap
   - Deck with 20 removal → detects excess

2. **Archetype matching**:
   - Burn deck → high match to "Burn" archetype
   - Control deck → low match to "Burn" archetype

3. **Explanation generation**:
   - Archetype staple → "appears in 87% of decks"
   - Role gap → "fills removal gap"

### Integration Tests

1. **End-to-end refinement**:
   - Partial Burn deck → suggests Lava Spike, Rift Bolt
   - Complete deck → suggests removals for weak cards

2. **Contextual discovery**:
   - Lightning Bolt → returns Lava Spike, Chain Lightning
   - Format filtering works

---

## Success Criteria

1. **Suggestions feel relevant** - Users understand why cards are suggested
2. **Role awareness works** - Doesn't suggest 10 removal spells
3. **Archetype context helps** - Modern Burn suggestions differ from Legacy
4. **Explanations are clear** - Users can make informed decisions

---

## Next Steps

1. ✅ Design complete
2. ⏳ Check if archetype staples already computed
3. ⏳ Implement Priority 1 (enhanced add suggestions)
4. ⏳ Test with real decks
5. ⏳ Iterate based on feedback
6. ⏳ Implement Priority 2-3

---

**Start with**: Enhance `suggest_additions` in `deck_completion.py` with role awareness and archetype filtering.

