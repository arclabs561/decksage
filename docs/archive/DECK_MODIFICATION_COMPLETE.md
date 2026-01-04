# Deck Modification System: Implementation Complete

**Date**: 2025-01-27
**Status**: ✅ Phase 1 & 2 Complete

---

## Summary

Implemented a comprehensive deck modification system with:
1. ✅ **Enhanced Add Suggestions** - Role-aware, archetype-aware, with explanations
2. ✅ **Remove Suggestions** - Identifies weak/redundant cards
3. ✅ **Replace Suggestions** - Functional alternatives, upgrades, downgrades

---

## What Was Built

### Phase 1: Enhanced Add Suggestions ✅

**Features**:
- Role gap detection (identifies missing removal, threats, etc.)
- Archetype staple boosting (cards in 70%+ of archetype decks)
- Constrained choice (max 10 suggestions)
- Explanation generation ("Archetype staple (87% inclusion)", "Fills removal gap")

**Code**: `src/ml/deck_building/deck_completion.py` - Enhanced `suggest_additions`

### Phase 2: Remove/Replace Suggestions ✅

**Features**:
- `suggest_removals`: Identifies weak cards (low archetype match) and redundant cards (excess role coverage)
- `suggest_replacements`: Finds functional alternatives, supports upgrade/downgrade modes
- Unified API endpoint with `action_type` parameter

**Code**:
- `src/ml/deck_building/deck_completion.py` - New functions
- `src/ml/api/api.py` - Enhanced endpoint

---

## API Usage

### Add Cards (Default)

```json
POST /v1/deck/suggest_actions
{
  "game": "magic",
  "deck": { /* deck */ },
  "action_type": "add",
  "archetype": "Burn",
  "top_k": 10
}
```

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

---

## Response Format

All actions return unified format:

```json
{
  "actions": [
    {
      "op": "add_card" | "remove_card" | "replace_card",
      "partition": "Main",
      "card": "Lava Spike",
      "count": 1,
      "score": 0.92,
      "reason": "Archetype staple (87% inclusion), fills removal gap",
      "target": "Opt"  // Only for replace_card
    }
  ],
  "metrics": {
    "top_k": 10,
    "elapsed_ms": 45,
    "action_type": "suggest",
    "num_actions": 8,
    "role_gaps": {"removal": 8, "threat": 6},
    "role_counts": {"removal": 4, "threat": 4}
  }
}
```

---

## Implementation Details

### Role Detection

Tracks functional roles:
- `removal`: Removal spells
- `threat`: Creatures/threats
- `card_draw`: Card draw spells
- `ramp`: Mana acceleration
- `counter`: Countermagic
- `tutor`: Tutors

**Gap Detection**: Compares current counts to targets (e.g., 10 removal, 14 threats)

### Archetype Boosting

Uses pre-computed `archetype_staples` data:
- Format: `{card: {archetype: inclusion_rate}}`
- Boosts cards with high inclusion rates (70%+)
- Up to 50% score boost for archetype staples

### Redundancy Detection

Identifies excess cards in roles:
- Thresholds: 12 removal, 20 threats, 10 card draw, etc.
- Suggests removing weakest cards (lowest archetype match)

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

## Testing

**Status**: ⏳ Ready for testing

**Test Cases**:
1. Partial Burn deck → suggests Lava Spike, Rift Bolt
2. Deck with no removal → prioritizes removal suggestions
3. Deck with excess removal → suggests removing weakest
4. Replace Opt → suggests Expressive Iteration (upgrade)

---

## Files Modified

1. `src/ml/deck_building/deck_completion.py`:
   - Enhanced `suggest_additions` (role-aware, archetype-aware)
   - Added `suggest_removals` (80 lines)
   - Added `suggest_replacements` (120 lines)

2. `src/ml/api/api.py`:
   - Added `action_type` to `SuggestActionsRequest`
   - Added `target` to `SuggestedAction`
   - Enhanced `suggest_actions` endpoint (unified handler)

---

**Status**: Phase 1 & 2 complete. Ready for testing and Phase 3 implementation.
