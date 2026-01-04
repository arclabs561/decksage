# Migration Guide: Adopting Data Validators

## Overview

This guide shows how to migrate existing code from unvalidated `json.loads()` to type-safe, validated Pydantic models.

## Which Data File to Use

**Use:** `data/processed/decks_with_metadata.jsonl` (132MB, 500K+ decks)
- ✅ format populated (Modern, Legacy, Standard, etc.)
- ✅ archetype populated (UR Aggro, Burn, Control, etc.)
- ❌ source null (but game detection still works via URL)

**Don't use:** `src/backend/decks_hetero.jsonl` (15MB, 57K decks)
- ❌ format empty (all become "Unknown")
- ❌ archetype empty
- ❌ source null

## Files to Update

### 1. `src/ml/llm_annotator.py`

**Before:**
```python
class LLMAnnotator:
    def _load_decks(self) -> list[dict]:
        """Load decks with metadata."""
        decks = []
        with open(PATHS.decks_with_metadata) as f:
            for line in f:
                if line.strip():
                    decks.append(json.loads(line))  # ❌ No validation
        return decks
```

**After:**
```python
from validators.loader import load_decks_lenient

class LLMAnnotator:
    def _load_decks(self) -> list[MTGDeck]:
        """Load decks with metadata and validation."""
        decks = load_decks_lenient(
            PATHS.decks_with_metadata,
            game="auto",
            check_legality=False,  # Skip expensive API calls
            verbose=False,
        )
        return decks
```

**Benefits:**
- ✅ Type safety (MTGDeck instead of dict)
- ✅ Format validation (catches bad decks)
- ✅ Automatic partition reconstruction
- ✅ Consistent data quality

**Type changes:**
```python
# Old: deck is dict[str, Any]
deck["cards"]  # Hope key exists
deck.get("format", "Unknown")

# New: deck is MTGDeck
deck.get_main_deck()  # Type-safe method
deck.format  # Always exists, validated
```

### 2. `src/ml/llm_data_validator.py`

**Before:**
```python
class DataQualityValidator:
    def _load_decks(self) -> list[dict]:
        """Load decks with metadata."""
        decks = []
        with open(PATHS.decks_with_metadata) as f:
            for line in f:
                if line.strip():
                    decks.append(json.loads(line))  # ❌ No validation
        return decks
```

**After:**
```python
from validators.loader import load_decks_lenient

class DataQualityValidator:
    def _load_decks(self) -> list[MTGDeck]:
        """Load decks with metadata and validation."""
        decks = load_decks_lenient(
            PATHS.decks_with_metadata,
            game="auto",
            check_legality=False,
            verbose=False,
        )
        return decks
```

**Note:** This class does semantic validation (LLM-based), so it expects dict, not MTGDeck. Two options:

**Option A:** Keep as dict (convert from MTGDeck):
```python
def _load_decks(self) -> list[dict]:
    validated_decks = load_decks_lenient(
        PATHS.decks_with_metadata,
        game="auto",
        check_legality=False,
        verbose=False,
    )
    # Convert back to dict for LLM processing
    return [deck.model_dump() for deck in validated_decks]
```

**Option B:** Update LLM code to use MTGDeck directly (better):
```python
def _load_decks(self) -> list[MTGDeck]:
    return load_decks_lenient(
        PATHS.decks_with_metadata,
        game="auto",
        check_legality=False,
        verbose=False,
    )

async def validate_archetype_sample(self, sample_size: int = 50):
    sample = random.sample(self.decks, min(sample_size, len(self.decks)))

    for deck in sample:
        # Old: deck["cards"]
        # New: deck.get_all_cards()
        cards = [c.name for c in deck.get_all_cards()]
        top_cards = cards[:15]

        prompt = f"""
Deck ID: {deck.deck_id}
Claimed Archetype: {deck.archetype or "Unknown"}
Format: {deck.format}
Top Cards: {", ".join(top_cards)}
...
"""
```

### 3. `src/ml/utils/data_loading.py`

**Before:**
```python
def load_decks_jsonl(
    jsonl_path: Path | None = None,
    sources: list[str] | None = None,
    max_placement: int | None = None,
    formats: list[str] | None = None,
) -> list[dict[str, Any]]:
    if jsonl_path is None:
        jsonl_path = PATHS.decks_with_metadata

    decks = []
    with open(jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            deck = json.loads(line)  # ❌ No validation

            # Apply filters
            if sources and deck.get("source") not in sources:
                continue  # ⚠️ Broken: source is always null!

            decks.append(deck)

    return decks
```

**After:**
```python
from validators.loader import load_decks_lenient
from validators.models import MTGDeck

def load_decks_jsonl(
    jsonl_path: Path | None = None,
    sources: list[str] | None = None,  # ⚠️ Not usable (source always null)
    max_placement: int | None = None,
    formats: list[str] | None = None,
) -> list[MTGDeck]:
    """
    Load and validate decks from JSONL.

    Note: source filtering not supported (source field is null in data).
    """
    if jsonl_path is None:
        jsonl_path = PATHS.decks_with_metadata

    # Load with validation
    all_decks = load_decks_lenient(
        jsonl_path,
        game="auto",
        check_legality=False,
        verbose=False,
    )

    # Apply filters
    filtered_decks = []
    for deck in all_decks:
        # Source filtering not supported (always null)
        if sources:
            print("Warning: source filtering not supported (source field is null)")

        # Placement filter
        if max_placement is not None:
            placement = deck.placement or 0
            if placement <= 0 or placement > max_placement:
                continue

        # Format filter
        if formats and deck.format not in formats:
            continue

        filtered_decks.append(deck)

    return filtered_decks
```

**Breaking changes:**
- Return type: `list[dict]` → `list[MTGDeck]`
- Source filtering: Doesn't work (prints warning)

**Compatibility shim** (if needed):
```python
def load_decks_jsonl_legacy(*args, **kwargs) -> list[dict]:
    """Legacy version that returns dicts for backward compatibility."""
    decks = load_decks_jsonl(*args, **kwargs)
    return [deck.model_dump() for deck in decks]
```

## Migration Steps

### Phase 1: Non-Breaking (Parallel Validators)

1. Keep existing `load_decks_jsonl()`
2. Add new `load_decks_jsonl_validated()` that returns MTGDeck
3. Update new code to use validated version
4. Test both in parallel

### Phase 2: Update Consumers

1. Update `llm_annotator.py` to use MTGDeck
2. Update `llm_data_validator.py` to use MTGDeck
3. Test each file individually
4. Update any scripts that import these

### Phase 3: Breaking Change

1. Update `load_decks_jsonl()` signature to return MTGDeck
2. Add `load_decks_jsonl_legacy()` shim if needed
3. Update all callers
4. Deprecate legacy version

## Testing Checklist

After each migration:

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Real data loads successfully
- [ ] Downstream code works (embeddings, similarity, etc.)
- [ ] Performance acceptable (no regressions)
- [ ] Linter happy

## Example: Complete Migration

**Before:**
```python
# Load data (no validation)
decks = []
with open(PATHS.decks_with_metadata) as f:
    for line in f:
        decks.append(json.loads(line))

# Access fields (hope they exist)
for deck in decks:
    format_name = deck.get("format", "Unknown")
    cards = deck.get("cards", [])
    print(f"{format_name}: {len(cards)} cards")
```

**After:**
```python
from validators.loader import load_decks_lenient

# Load data (validated)
decks = load_decks_lenient(
    PATHS.decks_with_metadata,
    game="auto",
    check_legality=False,
    verbose=True,
)

# Access fields (type-safe)
for deck in decks:
    format_name = deck.format  # Always exists
    main = deck.get_main_deck()
    print(f"{format_name}: {main.total_cards()} cards")
```

## Rollback Plan

If migration causes issues:

1. Revert file changes
2. Use legacy shim for compatibility
3. Keep validators separate until issues resolved
4. Gradual migration (one file at a time)

## Benefits Summary

### Before Migration
- ❌ No type safety
- ❌ No validation
- ❌ Hope data is good
- ❌ Runtime errors on bad data
- ❌ Manual partition reconstruction
- ❌ Inconsistent error handling

### After Migration
- ✅ Full type safety (IDE autocomplete)
- ✅ Automatic validation
- ✅ Know data is good
- ✅ Clear errors on bad data
- ✅ Automatic partition handling
- ✅ Consistent error handling

### Cost
- Initial migration: ~2 hours per file
- Type signature changes: Breaking for consumers
- Learning curve: Pydantic basics

### ROI
- Catch data errors early (before training)
- Prevent production bugs
- Better code maintainability
- Clear data quality metrics

---

**Status:** Ready for migration
**Risk:** Low (comprehensive tests, rollback plan)
**Recommended approach:** Gradual (one file at a time)
