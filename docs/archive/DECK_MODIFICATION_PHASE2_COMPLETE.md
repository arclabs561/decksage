# Deck Modification Phase 2: Remove/Replace Complete

**Date**: 2025-01-27  
**Status**: ✅ Phase 2 Complete

---

## Implemented: Remove and Replace Suggestions

### What Was Built

1. **`suggest_removals` Function**:
   - Identifies weak cards (low archetype match)
   - Detects redundant cards (multiple filling same role)
   - Preserves role coverage if requested
   - Returns (card, score, reason) tuples

2. **`suggest_replacements` Function**:
   - Finds functional alternatives (similar role)
   - Supports upgrade mode (better, more expensive)
   - Supports downgrade mode (cheaper alternatives)
   - Maintains role coverage
   - Boosts archetype staples

3. **Enhanced API Endpoint**:
   - Added `action_type` parameter: "add" | "remove" | "replace" | "suggest" (all)
   - Unified response format for all action types
   - Added `target` field to `SuggestedAction` for replace operations

---

## Implementation Details

### Remove Suggestions

**Strategy**:
1. **Low Archetype Match**: Cards not in archetype staples get high removal score (0.8)
2. **Low Inclusion Rate**: Cards in archetype but <30% inclusion get medium score (0.6)
3. **Redundant Roles**: Excess cards in a role (e.g., >12 removal) get removal suggestions

**Example**:
```python
removals = suggest_removals(
    game="magic",
    deck=my_deck,
    candidate_fn=cand_fn,
    archetype="Burn",
    archetype_staples=staples,
    preserve_roles=True,
)
# Returns: [
#   ("Opt", 0.8, "low_archetype_match"),
#   ("Lightning Helix", 0.7, "redundant_removal (excess removal cards)"),
# ]
```

### Replace Suggestions

**Strategy**:
1. **Functional Alternatives**: Cards with similar roles get boosted (1.2x)
2. **Upgrade Mode**: More expensive cards get boosted (1.3x)
3. **Downgrade Mode**: Cheaper cards get boosted (1.2x)
4. **Archetype Staples**: Cards in archetype get boosted (up to 30%)

**Example**:
```python
replacements = suggest_replacements(
    game="magic",
    deck=my_deck,
    card="Opt",
    candidate_fn=cand_fn,
    archetype="Burn",
    upgrade=True,  # Prefer better cards
)
# Returns: [
#   ("Expressive Iteration", 0.92, "upgrade ($0.50 → $2.00), archetype_staple (85%)"),
#   ("Consider", 0.88, "functional_alternative, archetype_staple (72%)"),
# ]
```

---

## API Usage

### Remove Cards

```json
POST /v1/deck/suggest_actions
{
  "game": "magic",
  "deck": { /* deck */ },
  "action_type": "remove",
  "archetype": "Burn",
  "top_k": 5
}
```

**Response**:
```json
{
  "actions": [
    {
      "op": "remove_card",
      "card": "Opt",
      "score": 0.8,
      "reason": "low_archetype_match"
    },
    {
      "op": "remove_card",
      "card": "Lightning Helix",
      "score": 0.7,
      "reason": "redundant_removal (excess removal cards)"
    }
  ]
}
```

### Replace Card

```json
POST /v1/deck/suggest_actions
{
  "game": "magic",
  "deck": { /* deck */ },
  "action_type": "replace",
  "seed_card": "Opt",
  "archetype": "Burn",
  "top_k": 5
}
```

**Response**:
```json
{
  "actions": [
    {
      "op": "replace_card",
      "card": "Expressive Iteration",
      "target": "Opt",
      "score": 0.92,
      "reason": "upgrade ($0.50 → $2.00), archetype_staple (85%)"
    }
  ]
}
```

### Suggest All (Add + Remove)

```json
POST /v1/deck/suggest_actions
{
  "game": "magic",
  "deck": { /* deck */ },
  "action_type": "suggest",
  "archetype": "Burn",
  "top_k": 10
}
```

**Response**: Returns both add and remove suggestions, sorted by score.

---

## Code Changes

**`src/ml/deck_building/deck_completion.py`**:
- Added `suggest_removals` function (80 lines)
- Added `suggest_replacements` function (120 lines)
- Exported both in `__all__`

**`src/ml/api/api.py`**:
- Added `action_type` field to `SuggestActionsRequest`
- Added `target` field to `SuggestedAction`
- Enhanced `suggest_actions` endpoint to handle all action types
- Unified response format

---

## Next Steps

### Phase 3: Contextual Discovery (Pending)

**Goal**: "What works with this card?"

**To Implement**:
1. `/cards/{card}/contextual` endpoint
2. Synergy detection (co-occurrence)
3. Alternative finding (functional similarity)
4. Upgrade/downgrade paths (price + power)

---

**Status**: Phase 2 complete. Ready for testing and Phase 3 implementation.

