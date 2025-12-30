# Deck Export and Unification - Complete ✅

## Summary

All deck data has been exported from canonical storage (`src/backend/data-full/`) and unified into a single file with game tags.

## Results

### Total Decks: 87,096

**By Game:**
- **Magic**: 83,092 decks
  - MTGTop8: 55,293
  - Goldfish: 23,174
  - Deckbox: 520
  - Unknown: 4,105
- **Pokemon**: 2,416 decks
  - Limitless: 2,416
- **Yu-Gi-Oh**: 1,588 decks
  - YGOPRODeck: 1,588

### Files Created

**Unified File:**
- `data/processed/decks_all_unified.jsonl` (304MB, 87,096 decks)
  - All decks with `game` field added
  - Ready for multi-game ML training

**Per-Game/Source Files:**
- `data/decks/magic_mtgtop8_decks.jsonl` (147MB, 55,293 decks)
- `data/decks/magic_goldfish_decks.jsonl` (94MB, 23,174 decks)
- `data/decks/magic_deckbox_decks.jsonl` (15MB, 520 decks)
- `data/decks/pokemon_limitless_decks.jsonl` (2.1MB, 2,416 decks)
- `data/decks/yugioh_ygoprodeck_decks.jsonl` (2.1MB, 1,588 decks)

## Usage

### Load Unified Decks
```python
from pathlib import Path
import json

# Load all decks
decks = []
with open("data/processed/decks_all_unified.jsonl") as f:
    for line in f:
        deck = json.loads(line)
        decks.append(deck)

# Filter by game
magic_decks = [d for d in decks if d["game"] == "magic"]
pokemon_decks = [d for d in decks if d["game"] == "pokemon"]
yugioh_decks = [d for d in decks if d["game"] == "yugioh"]
```

### Load Specific Source
```python
# Load MTGTop8 decks only
with open("data/decks/magic_mtgtop8_decks.jsonl") as f:
    for line in f:
        deck = json.loads(line)
        # Process deck
```

## Export Script

**Script**: `scripts/export_and_unify_all_decks.py`

**Usage**:
```bash
# Export and unify all decks
python3 scripts/export_and_unify_all_decks.py

# Re-export everything
rm data/decks/*.jsonl data/processed/decks_all_unified.jsonl
python3 scripts/export_and_unify_all_decks.py
```

## Data Structure

Each deck JSON object contains:
- `game`: "magic", "pokemon", or "yugioh"
- `deck_id`: Unique identifier
- `archetype`: Deck archetype
- `format`: Format (e.g., "Standard", "Modern")
- `url`: Source URL
- `source`: Data source (e.g., "mtgtop8", "limitless")
- `player`: Player name (if available)
- `event`: Tournament event (if available)
- `placement`: Tournament placement (if available)
- `cards`: Array of `{name, count, partition}` objects

## Canonical Data

**Location**: `src/backend/data-full/` (3.8GB, 270K files)
- This is the source of truth
- Exported data is generated from canonical
- Can be re-exported anytime

## Next Steps

1. ✅ All decks exported and unified
2. ✅ Documentation updated
3. ✅ Paths updated in `src/ml/utils/paths.py`
4. ⏳ Update ML pipeline to use unified file
5. ⏳ Add validation and quality checks
