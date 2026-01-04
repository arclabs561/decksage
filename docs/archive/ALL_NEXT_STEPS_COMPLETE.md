# All Next Steps - Complete Execution Summary

## ✅ Completed This Session

### 1. Data Download & Verification
- ✅ Downloaded `magic_128d_test_pecanpy.wv` (14.2 MB) from S3
- ✅ Downloaded `pairs_large.csv` (266 MB) from S3
- ✅ Verified test set exists: `experiments/test_set_canonical_magic.json` (38 queries)

### 2. Infrastructure Created
- ✅ `src/ml/utils/name_normalizer.py` - Name normalization utilities with `NameMapper` class
- ✅ `src/ml/scripts/fix_name_normalization_standalone.py` - Standalone name mapping script (avoids scipy)
- ✅ `src/ml/scripts/evaluate_all_embeddings.py` - Updated with name mapping support
- ✅ `src/ml/scripts/export_decks_metadata.py` - Metadata export script
- ✅ `src/ml/scripts/compute_and_cache_signals.py` - Signal computation script (already existed)

### 3. Integration Complete
- ✅ Name mapper integrated into evaluation pipeline
- ✅ All scripts ready for sequential execution
- ✅ Documentation created

## ⏳ Pending Execution (Blocked by Environment)

### Step 1: Generate Name Mapping
**Script**: `fix_name_normalization_standalone.py` ✅ Ready
**Blocked by**: scipy build issue preventing dependency installation
**Command** (after fix):
```bash
cd /Users/arc/Documents/dev/decksage
uv run --script src/ml/scripts/fix_name_normalization_standalone.py \
  --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
  --test-set experiments/test_set_canonical_magic.json \
  --output experiments/name_mapping.json
```

### Step 2: Test Evaluation with Name Mapping
**Script**: `evaluate_all_embeddings.py` ✅ Ready (updated)
**Prerequisite**: Name mapping file from Step 1
**Command**:
```bash
uv run --script src/ml/scripts/evaluate_all_embeddings.py \
  --name-mapping experiments/name_mapping.json \
  --embeddings-dir data/embeddings \
  --output experiments/embedding_evaluation_with_mapping.json
```

### Step 3: Export Decks Metadata
**Script**: `export_decks_metadata.py` ✅ Ready
**Status**: Data directory not found locally (`src/backend/data-full/games/magic`)
**Options**:
- Export on AWS EC2 if data exists there
- Download raw data first
- Check S3 for existing metadata

### Step 4: Compute Signals
**Script**: `compute_and_cache_signals.py` ✅ Ready
**Blocked by**:
1. Missing `decks_with_metadata.jsonl` (prerequisite from Step 3)
2. scipy build issue (environment)
**Solution**: Run on AWS EC2 after metadata is available

## 🔧 Environment Fix Required

### Primary Blocker: scipy Build Failure
```
ERROR: Dependency "OpenBLAS" not found
```

**Quick Fix**:
```bash
brew install openblas
export OPENBLAS=$(brew --prefix openblas)
uv sync
```

**Alternative**: Use AWS EC2 (recommended for immediate progress)

## Execution Sequence (After Environment Fix)

1. **Generate Name Mapping** (~5-10 min)
   - Analyzes mismatches between test set and embeddings/graph
   - Creates mapping for consistent name resolution
   - Output: `experiments/name_mapping.json`

2. **Test Evaluation** (~2-5 min)
   - Runs evaluation with name mapping
   - Verifies fixes improve hit rate
   - Output: `experiments/embedding_evaluation_with_mapping.json`

3. **Export Metadata** (if data available)
   - Exports decks with archetype/format metadata
   - Required for signal computation
   - Output: `data/processed/decks_with_metadata.jsonl`

4. **Compute Signals** (~10-30 min)
   - Sideboard co-occurrence
   - Temporal (monthly) co-occurrence
   - Archetype staples and co-occurrence
   - Format-specific patterns
   - Output: `experiments/signals/*.json`

## Files Status

| File | Status | Location/Size |
|------|--------|--------------|
| `magic_128d_test_pecanpy.wv` | ✅ Downloaded | data/embeddings/ (14.2 MB) |
| `pairs_large.csv` | ✅ Downloaded | data/processed/ (266 MB) |
| `test_set_canonical_magic.json` | ✅ Verified | experiments/ (38 queries) |
| `name_mapping.json` | ⏳ Pending | experiments/ (needs execution) |
| `decks_with_metadata.jsonl` | ❌ Missing | data/processed/ (needs export) |
| Signal files | ⏳ Pending | experiments/signals/ (needs computation) |

## Ready for Execution

All infrastructure is complete:
- ✅ Scripts created and ready
- ✅ Data downloaded and verified
- ✅ Integration complete
- ⏳ Waiting on environment fix or AWS execution

**Next Action**: Fix scipy build (`brew install openblas`) OR execute on AWS EC2

Once environment is ready, all steps can execute sequentially and complete the remaining tasks.
