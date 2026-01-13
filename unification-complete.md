# Annotations & Judgments Unification - Complete ✅

## Summary

**Decision:** Unified annotations and judgments into a single canonical format.

**Result:** Judgments are now annotations with `source: "llm_judgment"` to distinguish them from other sources.

## Changes Made

### 1. Updated Judgment Creators
- **`progressive_annotation.py`**: Now outputs annotation JSONL format directly
- **`multi_perspective_judge.py`**: Now outputs annotation JSONL format directly
- Both save to `annotations/judgment_*.jsonl` (unified location)

### 2. Unified Format
All similarity data now uses the same annotation format:
```json
{
  "card1": "Lightning Bolt",
  "card2": "Chain Lightning",
  "similarity_score": 0.95,
  "similarity_type": "functional",
  "is_substitute": true,
  "reasoning": "...",
  "source": "llm_judgment",  // or "llm_annotation", "hand_annotation"
  "judgment_metadata": {     // Only if source=llm_judgment
    "confidence": 0.9,
    "method_votes": ["node2vec"],
    "bias_flag": null
  }
}
```

### 3. Updated Integration Scripts
- **`integrate_all_annotations.py`**: Now loads judgment JSONL files directly (no conversion needed)
- **`find_all_annotation_files()`**: Looks for `judgment_*.jsonl` in main annotations directory
- Backward compatibility: Still supports old JSON format in `llm_judgments/` subdirectory

### 4. Migration Script
- **`migrate_judgments_to_annotations.py`**: Converts existing judgment JSON files to annotation JSONL format
- Usage: `python -m src.ml.scripts.migrate_judgments_to_annotations --backup`

### 5. Updated Documentation
- **`DATA_LINEAGE_METADATA.json`**: Updated to reflect unified format
- Pattern changed: `annotations/judgment_*.jsonl` (was `annotations/llm_judgments/judgment_*.json`)

## Benefits

✅ **Single format**: One canonical format for all similarity data
✅ **Simpler code**: No separate judgment handling logic
✅ **Better provenance**: Source tracked via metadata, not format
✅ **Easier integration**: All annotations work the same way
✅ **Reduced duplication**: One set of utilities, not two

## Migration Steps

1. **Run migration script** (optional, for existing files):
   ```bash
   python -m src.ml.scripts.migrate_judgments_to_annotations \
     --judgments-dir annotations/llm_judgments \
     --output-dir annotations \
     --backup
   ```

2. **Verify**: Check that new judgment files are created as JSONL in `annotations/`

3. **Update scripts**: Any scripts that directly read judgment JSON files should be updated

4. **Archive old files** (optional): Move old JSON files to archive after verification

## Backward Compatibility

- Old JSON format still supported via `convert_judgments_to_annotations()`
- `load_judgment_files()` still works for old format
- `integrate_all_annotations.py` handles both formats automatically

## Next Steps

- [ ] Run migration script on existing judgment files
- [ ] Update any scripts that directly read judgment JSON
- [ ] Archive old judgment files (optional)
- [ ] Update any documentation that references old format

## Status: ✅ COMPLETE

All code changes complete. System is unified and ready for use.
