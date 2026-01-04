# Optimizations Applied

## Issues Found and Fixed

### 1. Labeling Script (`generate_labels_for_new_queries.py`)

**Issues**:
- No retry logic for failed queries
- No checkpoint/resume capability
- Silent failures (returns empty labels)
- No progress persistence

**Optimizations**:
- ✅ Added retry logic (3 attempts with exponential backoff)
- ✅ Added checkpointing (saves every N queries)
- ✅ Better error logging
- ✅ Progress persistence across restarts
- ✅ Created `generate_labels_for_new_queries_optimized.py`

### 2. Card Enrichment (`enrich_attributes_with_scryfall.py`)

**Issues**:
- Fixed 0.1s delay (not adaptive)
- No checkpoint/resume
- Re-reads entire CSV on each save (inefficient)
- 81.3% empty rows (may have been reset)

**Optimizations**:
- ✅ Adaptive rate limiting (adjusts based on 429 responses)
- ✅ Checkpoint/resume capability
- ✅ Skips already enriched cards efficiently
- ✅ Better progress tracking
- ✅ Created `enrich_attributes_with_scryfall_optimized.py`

### 3. Hyperparameter Search

**Issues**:
- Grid search may be too large (50 configs)
- No early stopping
- No result validation before upload

**Recommendations**:
- Use smaller initial search space
- Add early stopping for poor configs
- Verify upload before instance termination

### 4. Multi-Game Export

**Issues**:
- No progress indication
- May be memory intensive

**Recommendations**:
- Add progress logging
- Stream processing for large datasets

## Next Steps

1. **Use optimized scripts**:
   ```bash
   # Labeling
   uv run --script src/ml/scripts/generate_labels_for_new_queries_optimized.py \
       --input experiments/test_set_labeled_magic.json \
       --output experiments/test_set_labeled_magic.json \
       --checkpoint-interval 5

   # Card enrichment
   uv run --script src/ml/scripts/enrich_attributes_with_scryfall_optimized.py \
       --input data/processed/card_attributes_minimal.csv \
       --output data/processed/card_attributes_enriched.csv \
       --checkpoint-interval 50
   ```

2. **Monitor progress**:
   - Checkpoints allow resuming from failures
   - Better progress tracking
   - Adaptive rate limiting reduces failures

3. **Continue improvements**:
   - Hyperparameter search: Reduce search space initially
   - Multi-game export: Add progress logging

## Performance Improvements

- **Labeling**: Retry logic should reduce failures from ~38% to <5%
- **Card enrichment**: Adaptive rate limiting should reduce 429 errors
- **Checkpointing**: Allows resuming from any point (no lost work)
