# Deck Modification Implementation Status

**Date**: 2025-01-27  
**Status**: ✅ Phase 1 Complete - Enhanced Add Suggestions

---

## Completed: Enhanced Add Suggestions

### What Was Implemented

1. **Role-Aware Filtering**:
   - Detects functional role gaps in deck (removal, threats, card draw, etc.)
   - Boosts suggestions that fill identified gaps
   - Prevents suggesting 10 removal spells when deck already has enough

2. **Archetype Context**:
   - Accepts `archetype` parameter in `SuggestActionsRequest`
   - Boosts archetype staples (cards appearing in 70%+ of archetype decks)
   - Uses pre-computed `archetype_staples` data from API state

3. **Constrained Choice**:
   - Limits suggestions to `max_suggestions` (default 10)
   - Prevents overwhelming users with too many options

4. **Explanation Generation**:
   - Tracks why each card scored well
   - Returns explanations in metrics: "Archetype staple (87% inclusion)", "Fills removal gap"
   - Includes explanations in API response `reason` field

### Code Changes

**`src/ml/deck_building/deck_completion.py`**:
- Added `archetype`, `archetype_staples`, `role_aware`, `max_suggestions` parameters to `suggest_additions`
- Implemented role gap detection
- Added archetype staple boosting
- Added score reason tracking
- Limited results to `max_suggestions`

**`src/ml/api/api.py`**:
- Added `archetype` field to `SuggestActionsRequest`
- Updated `suggest_actions` endpoint to pass archetype and archetype_staples
- Enhanced reason generation to use score_reasons from metrics

### How It Works

1. **Role Detection**:
   ```python
   # Counts cards by functional role
   role_counts = {"removal": 3, "threat": 8, "card_draw": 2}
   role_gaps = {"removal": 7, "card_draw": 4}  # Target - current
   ```

2. **Archetype Boosting**:
   ```python
   if card in archetype_staples[archetype]:
       inclusion_rate = archetype_staples[card][archetype]  # e.g., 0.87
       boost = 1.0 + (inclusion_rate * 0.5)  # Up to 50% boost
   ```

3. **Role Gap Boosting**:
   ```python
   if card fills role gap:
       boost = 1.0 + (gap_size / 10.0) * 0.3  # Up to 30% boost
   ```

### Example Usage

```python
POST /v1/deck/suggest_actions
{
  "game": "magic",
  "deck": {
    "partitions": [{
      "name": "Main",
      "cards": [
        {"name": "Lightning Bolt", "count": 4},
        {"name": "Monastery Swiftspear", "count": 4}
      ]
    }]
  },
  "archetype": "Burn",
  "top_k": 10
}
```

**Response**:
```json
{
  "actions": [
    {
      "op": "add_card",
      "card": "Lava Spike",
      "score": 0.92,
      "reason": "Archetype staple (87% inclusion), fills removal gap"
    },
    {
      "op": "add_card",
      "card": "Rift Bolt",
      "score": 0.88,
      "reason": "Archetype staple (82% inclusion)"
    }
  ],
  "metrics": {
    "role_gaps": {"removal": 8, "threat": 6},
    "role_counts": {"removal": 4, "threat": 4},
    "score_reasons": {
      "Lava Spike": "Archetype staple (87% inclusion), fills removal gap",
      "Rift Bolt": "Archetype staple (82% inclusion)"
    }
  }
}
```

---

## Next Steps

### Phase 2: Remove/Replace Suggestions (Pending)

**Goal**: Help users identify weak/redundant cards

**To Implement**:
1. `suggest_removals` function
2. Weak card detection (low archetype match)
3. Redundancy detection (multiple cards filling same role)
4. Format legality checks

### Phase 3: Contextual Discovery (Pending)

**Goal**: "What works with this card?"

**To Implement**:
1. `/cards/{card}/contextual` endpoint
2. Synergy detection (co-occurrence)
3. Alternative finding (functional similarity)
4. Upgrade/downgrade paths (price + power)

---

## Testing

**Status**: ⏳ Pending

**Test Cases Needed**:
1. Partial Burn deck → suggests Lava Spike, Rift Bolt
2. Deck with no removal → prioritizes removal suggestions
3. Deck with archetype context → boosts archetype staples
4. Budget constraints → filters by price

---

## Dependencies

**Required Data**:
- ✅ Archetype staples: `experiments/signals/archetype_staples.json`
- ✅ Functional tagger: For role detection
- ⏳ Format-specific archetype data: For format filtering

**Note**: Archetype staples must be computed first using `compute_and_cache_signals.py`

---

**Status**: Ready for testing. Implementation complete for Phase 1.

