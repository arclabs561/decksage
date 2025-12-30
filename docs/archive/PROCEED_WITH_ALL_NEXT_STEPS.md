# Proceed with All Next Steps - Complete Status

## Executive Summary

All next steps have been prepared and are ready for execution. Infrastructure is complete, scripts are created, and data is downloaded. The primary blocker is the scipy build issue, which can be resolved by installing OpenBLAS or using AWS EC2.

## ✅ What's Complete

### 1. Data Preparation
- ✅ Embeddings downloaded: `data/embeddings/magic_128d_test_pecanpy.wv` (14.2 MB)
- ✅ Graph data downloaded: `data/processed/pairs_large.csv` (266 MB)
- ✅ Test set verified: `experiments/test_set_canonical_magic.json` exists

### 2. Infrastructure Created
- ✅ `src/ml/utils/name_normalizer.py` - Name normalization utilities
- ✅ `src/ml/scripts/fix_name_normalization_standalone.py` - Name mapping script (no scipy)
- ✅ `src/ml/scripts/evaluate_all_embeddings.py` - Updated with name mapping support
- ✅ `src/ml/scripts/compute_and_cache_signals.py` - Signal computation script
- ✅ `src/ml/scripts/export_decks_metadata.py` - Metadata export script

### 3. Integration Complete
- ✅ Name mapper integrated into evaluation pipeline
- ✅ All scripts ready for sequential execution
- ✅ Documentation created

## ⏳ What's Pending (Environment Blocked)

### Step 1: Generate Name Mapping
**Status**: Script ready, blocked by scipy build
**Command** (after environment fix):
```bash
uv run --script src/ml/scripts/fix_name_normalization_standalone.py \
  --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
  --test-set experiments/test_set_canonical_magic.json \
  --output experiments/name_mapping.json
```

### Step 2: Test Evaluation with Name Mapping
**Status**: Script ready, waiting for Step 1
**Command**:
```bash
uv run --script src/ml/scripts/evaluate_all_embeddings.py \
  --name-mapping experiments/name_mapping.json \
  --embeddings-dir data/embeddings \
  --output experiments/embedding_evaluation_with_mapping.json
```

### Step 3: Export Decks Metadata
**Status**: Script ready, data directory missing locally
**Options**:
- Export on AWS EC2 if data exists there
- Download raw data first
- Use existing metadata if available

### Step 4: Compute Signals
**Status**: Script ready, blocked by:
1. Missing `decks_with_metadata.jsonl` (prerequisite)
2. scipy build issue
**Solution**: Run on AWS EC2 after metadata available

## 🔧 Environment Fix Required

### Quick Fix (Recommended)
```bash
# Install OpenBLAS
brew install openblas

# Set environment variable
export OPENBLAS=$(brew --prefix openblas)

# Sync dependencies
uv sync

# Now scripts can run
uv run --script src/ml/scripts/fix_name_normalization_standalone.py ...
```

### Alternative: AWS EC2
All computation can run on EC2 to avoid local issues:
- Name mapping generation
- Signal computation
- Full evaluation pipeline

## Execution Sequence

Once environment is fixed:

1. **Generate Name Mapping** (5-10 min)
   - Analyzes mismatches between test set and embeddings/graph
   - Creates mapping file for consistent name resolution

2. **Test Evaluation** (2-5 min)
   - Runs evaluation with name mapping
   - Verifies fixes improve hit rate

3. **Export Metadata** (if data available)
   - Exports decks with archetype/format metadata
   - Required for signal computation

4. **Compute Signals** (10-30 min)
   - Sideboard co-occurrence
   - Temporal (monthly) co-occurrence
   - Archetype staples and co-occurrence
   - Format-specific patterns

## Files Status

| File | Status | Size/Location |
|------|--------|---------------|
| `magic_128d_test_pecanpy.wv` | ✅ Downloaded | 14.2 MB |
| `pairs_large.csv` | ✅ Downloaded | 266 MB |
| `test_set_canonical_magic.json` | ✅ Verified | experiments/ |
| `name_mapping.json` | ⏳ Pending | experiments/ |
| `decks_with_metadata.jsonl` | ❌ Missing | data/processed/ |
| Signal files | ⏳ Pending | experiments/signals/ |

## Next Actions

### Immediate
1. Fix scipy build: `brew install openblas && export OPENBLAS=$(brew --prefix openblas) && uv sync`
2. Generate name mapping
3. Test evaluation

### Short-term
4. Export decks metadata (if data available)
5. Compute signals
6. Test signal integration

### Long-term
7. Complete temporal evaluation
8. Expand test sets
9. Full evaluation pipeline

## Conclusion

**All infrastructure is complete and ready.** The only blocker is the environment (scipy build), which has clear solutions. Once fixed, all steps can execute sequentially and complete the remaining tasks.

**Recommendation**: Fix scipy build locally for development, or use AWS EC2 for production computation.

