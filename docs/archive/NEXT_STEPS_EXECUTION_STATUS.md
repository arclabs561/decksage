# Next Steps Execution Status

## Completed Steps

### 1. Data Download ✅
- Downloaded `magic_128d_test_pecanpy.wv` (14.2 MB) from S3
- Downloaded `pairs_large.csv` (266 MB) from S3
- Both files verified and accessible

### 2. Name Normalization Infrastructure ✅
- Created `src/ml/utils/name_normalizer.py` with `NameMapper` class
- Integrated name mapper into `evaluate_all_embeddings.py`
- Created standalone script `fix_name_normalization_standalone.py` (no scipy dependency)

## In Progress

### 3. Generate Name Mapping (Running)
- Script: `fix_name_normalization_standalone.py`
- Inputs:
  - Test set: `experiments/test_set_canonical_magic.json` ✅
  - Embeddings: `data/embeddings/magic_128d_test_pecanpy.wv` ✅
  - Graph: `data/processed/pairs_large.csv` ✅
- Output: `experiments/name_mapping.json` (in progress)

## Blockers & Workarounds

### Blocker: scipy Build Issue
- **Issue**: scipy fails to build due to missing OpenBLAS (Python 3.13 compatibility)
- **Impact**: Blocks scripts that depend on `sentence-transformers` (which requires scipy)
- **Workaround**:
  - Created standalone scripts that avoid scipy
  - Can use AWS EC2 for computation-heavy tasks
  - Alternative: Use pre-built wheels or conda environment

### Missing: decks_with_metadata.jsonl
- **Status**: Not found locally or on S3
- **Impact**: Blocks signal computation (sideboard, temporal, archetype, format)
- **Solution**:
  - Export from raw data using `export-hetero` command (requires data directory)
  - Or generate on AWS EC2 if data exists there

## Next Steps (After Name Mapping Completes)

1. **Test Evaluation with Name Mapping**
   ```bash
   uv run --script src/ml/scripts/evaluate_all_embeddings.py \
     --name-mapping experiments/name_mapping.json \
     --embeddings-dir data/embeddings
   ```

2. **Export Decks Metadata** (if data available)
   ```bash
   cd src/backend
   go run cmd/export-hetero/main.go \
     data-full/games/magic \
     ../../data/processed/decks_with_metadata.jsonl
   ```

3. **Compute Signals** (after metadata available)
   - Run on AWS EC2 to avoid scipy issue
   - Or fix scipy build locally first

4. **Complete Temporal Implementation**
   - Finish `temporal_context_capture.py`
   - Integrate into evaluation framework

## Files Created

- `src/ml/utils/name_normalizer.py` - Name normalization utilities
- `src/ml/scripts/fix_name_normalization_standalone.py` - Standalone name mapping script
- `src/ml/scripts/export_decks_metadata.py` - Export decks metadata
- `CONTINUING_PROGRESS.md` - Progress documentation
- `NEXT_STEPS_EXECUTION_STATUS.md` - This file

## Current Status Summary

- ✅ Data downloaded and verified
- ✅ Infrastructure created
- 🔄 Name mapping generation in progress
- ⏳ Evaluation testing pending (waiting for mapping)
- ⏳ Signal computation pending (waiting for metadata)
- ⏳ Temporal implementation pending
