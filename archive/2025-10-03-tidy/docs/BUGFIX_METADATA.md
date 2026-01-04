# Critical Bug Fix: Metadata Parsing

## Date: October 2, 2025

## The Bug

**Blocked 53 experiments** from accessing deck metadata (archetype, format).

## Root Cause

JSON structure mismatch between Go extraction and Python consumption.

**Actual structure (from Go scraper):**
```json
{
  "id": "...",
  "type": {
    "inner": {
      "archetype": "Burn",
      "format": "Modern"
    }
  },
  "partitions": [...]
}
```

**What Python code expected:**
```json
{
  "collection": {
    "type": {
      "inner": {
        "archetype": "Burn",
        "format": "Modern"
      }
    }
  }
}
```

The `collection` wrapper **never existed** in the files.

## Why It Took 53 Experiments to Find

1. **Silent error handling**: Go export tool used `_, _ =` everywhere, ignoring errors
2. **No diagnostics**: Tools returned 0 results with no explanation
3. **Circular attempts**: Tried fixing Python parsing 7 times, never checked Go extraction
4. **Design over debugging**: Wrote 4 design documents requiring metadata instead of fixing the bug

## The Fix

**File**: `src/backend/cmd/export-hetero/main.go`

```diff
- col, ok := obj["collection"].(map[string]interface{})
- if !ok {
-     continue
- }
- URL: getString(col, "url")

+ // FIXED: Data is at root level, not under "collection"
+ URL: getString(obj, "url")
```

## Results After Fix

**Before:**
- exp_046: 0 decks with metadata (P@10 = 0.0)
- All heterogeneous graph experiments failed
- Design docs with no implementation

**After:**
```bash
✓ Exported 4718 decks with full context
  With archetype: 4718 (100%)
  With format: 4718 (100%)
```

## Files Fixed

- `src/backend/cmd/export-hetero/main.go` - Removed `collection` wrapper assumption
- `src/backend/cmd/diagnose-metadata/main.go` - New diagnostic tool with proper error reporting

## Data Generated

- `data/processed/decks_with_metadata.jsonl` - 4,718 decks with full structure
- Each deck has: archetype, format, cards with partitions (main/sideboard)

## What This Unlocks

All the experiments that failed due to "metadata parsing fails":
- exp_007, exp_019, exp_025, exp_028, exp_036, exp_046

Can now be re-run successfully with:
- Archetype-aware similarity
- Format-specific embeddings
- Heterogeneous graph (Card-Deck-Archetype)
- All designs from design documents

## Lessons

1. **Check assumptions first**: "Collection wrapper exists" was never verified
2. **Don't ignore errors**: Silent failures hide problems
3. **Debug before designing**: One debugging session > 4 design documents
4. **Test error paths**: Add diagnostics that report failures, not just silently return zeros

## Next Steps

With metadata now accessible:
1. Re-implement heterogeneous graph properly
2. Run archetype-aware experiments
3. Expected: P@10 > 0.14 (beat 53-experiment baseline)
