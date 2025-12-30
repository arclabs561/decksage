# Pipeline Coherence Review - Complete

## S3 Usage ✅

### Bucket Structure
- **Bucket**: `s3://games-collections`
- **Structure**:
  ```
  s3://games-collections/
  ├── processed/          # Processed datasets
  │   ├── pairs_large.csv
  │   ├── pairs_multi_game.csv
  │   ├── decks_all_final.jsonl ✅ NEW
  │   ├── card_attributes_enriched.csv
  │   └── ...
  ├── embeddings/         # Trained embeddings
  │   ├── production.wv
  │   └── ...
  ├── experiments/        # Test sets and results
  │   ├── test_set_canonical_*.json
  │   └── ...
  └── graphs/             # Graph edgelists
      └── ...
  ```

### Sync Scripts
- `scripts/sync_all_to_s3.sh` - Comprehensive sync (updated)
- `scripts/sync_to_s3.sh` - Selective sync (updated)

## Dataset Paths ✅

### Canonical Paths (paths.py)
All scripts should use `PATHS` from `src/ml/utils/paths.py`:

```python
from ml.utils.paths import PATHS

# Training data
pairs = PATHS.pairs_large
decks = PATHS.decks_all_final  # ✅ Use final enhanced version

# Test sets
test_magic = PATHS.test_magic
test_pokemon = PATHS.test_pokemon
test_yugioh = PATHS.test_yugioh

# Embeddings
embedding = PATHS.embedding("production")
```

### Actual Files
- ✅ `pairs_large.csv` (265 MB, 7.5M pairs) - Primary training data
- ✅ `pairs_multi_game.csv` (1.6 GB, 24.6M pairs) - Multi-game (MTG-only currently)
- ✅ `decks_all_final.jsonl` (241 MB, 69K decks) - **RECOMMENDED** for deck-based training
- ✅ `decks_all_unified.jsonl` (292 MB, 87K decks) - Raw unified (before enhancement)
- ✅ `decks_all_enhanced.jsonl` (241 MB, 69K decks) - Enhanced (normalized, deduplicated)
- ✅ `card_attributes_enriched.csv` (6 MB, 27K cards)

## Training Pipeline

### Data Flow
```
Canonical Data (src/backend/data-full/)
    ↓
Export (bin/export-hetero)
    ↓
Unified (decks_all_unified.jsonl)
    ↓
Enhance (scripts/enhance_exported_decks.py)
    ↓
Final (decks_all_final.jsonl) ✅ USE THIS
    ↓
Training Scripts
    ↓
Embeddings (data/embeddings/*.wv)
```

### Training Data Recommendations

**For Co-occurrence Training:**
- Use: `pairs_large.csv` (7.5M pairs, MTG)
- S3: `s3://games-collections/processed/pairs_large.csv`

**For Multi-game Training:**
- Use: `pairs_multi_game.csv` (24.6M pairs, currently MTG-only)
- S3: `s3://games-collections/processed/pairs_multi_game.csv`
- Note: Name is misleading - contains only MTG data

**For Deck-based Training:**
- Use: `decks_all_final.jsonl` (69K decks, all games, enhanced) ✅
- S3: `s3://games-collections/processed/decks_all_final.jsonl`
- Features: Normalized, deduplicated, validated

### Training Scripts

**Local Training:**
- Input: Local paths (`data/processed/pairs_large.csv`)
- Output: `data/embeddings/*.wv`

**AWS Training (RunCtl):**
- Input: S3 paths (`s3://games-collections/processed/pairs_large.csv`)
- Output: S3 paths (`s3://games-collections/embeddings/`)
- Use: `just train-aws <instance>`

**AWS Training (Direct):**
- Input: S3 paths or local (uploaded to S3)
- Output: S3 paths
- Use: `src/ml/scripts/run_improved_training_on_aws.py`

## Evaluation Pipeline

### Test Sets

**Canonical (Recommended for Production):**
- `experiments/test_set_canonical_magic.json` (38 queries)
- `experiments/test_set_canonical_pokemon.json` (10 queries)
- `experiments/test_set_canonical_yugioh.json` (13 queries)

**Expanded (For Comprehensive Analysis):**
- `experiments/test_set_expanded_magic.json` (various sizes)
- `experiments/test_set_expanded_pokemon.json`
- `experiments/test_set_expanded_yugioh.json`

**Ground Truth:**
- `data/processed/ground_truth_v1.json` (38 queries, Magic only)

### Evaluation Scripts

**Multi-game Evaluation:**
- `evaluate_all_games.py` - Evaluates on all games
- Uses: Canonical test sets

**Comprehensive Evaluation:**
- `comprehensive_final_evaluation.py` - Full evaluation suite
- Uses: Expanded test sets + substitution tests

**Embedding Comparison:**
- `evaluate_all_embeddings.py` - Compare all embeddings
- Uses: Canonical test sets

### Recommended Evaluation Flow
```
1. Load embedding (production.wv or experimental)
2. Load canonical test set (PATHS.test_magic, etc.)
3. Run evaluation
4. Save results to experiments/
5. Sync to S3
```

## Embeddings

### Production
- `data/embeddings/production.wv` - Current production embedding
- S3: `s3://games-collections/embeddings/production.wv`

### Experimental
- 22 embedding files in `data/embeddings/`
- See `data/embeddings/README.md` for inventory

## Issues Found & Fixed

### ✅ Fixed
1. Updated `paths.py` with `decks_all_enhanced` and `decks_all_final`
2. Updated sync scripts to include new deck files
3. Documented S3 structure

### ⚠️ Recommendations
1. **Migrate scripts to use PATHS** instead of hardcoded paths
   - 21 scripts use hardcoded `pairs_large.csv`
   - 16 scripts use hardcoded `test_set_canonical_magic.json`
   - Consider creating migration script

2. **Standardize on canonical test sets** for production
   - Some scripts use expanded, some use canonical
   - Document which to use when

3. **Update training scripts** to use `decks_all_final.jsonl`
   - Some still reference `decks_with_metadata.jsonl`
   - New enhanced version is better

## Coherence Status

✅ **S3 Usage**: Consistent bucket, clear structure
✅ **Dataset Paths**: Well-defined in paths.py
✅ **Training Pipeline**: Clear data flow
✅ **Evaluation Pipeline**: Multiple test sets available
✅ **Sync Scripts**: Updated to include new files
⚠️ **Script Migration**: Some hardcoded paths remain (non-critical)

## Data Flow Summary

```
┌─────────────────────────────────────┐
│ Canonical Data                      │
│ src/backend/data-full/              │
│ (3.8GB, 270K files)                 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Export & Unify                      │
│ scripts/export_and_unify_all_decks  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Enhanced Decks                      │
│ decks_all_final.jsonl (69K decks)   │
└──────────────┬──────────────────────┘
               │
               ├──────────────────────┐
               ▼                      ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Training             │  │ Evaluation           │
│ - pairs_large.csv    │  │ - canonical test sets │
│ - decks_all_final    │  │ - expanded test sets │
└──────────┬───────────┘  └──────────┬───────────┘
           │                         │
           ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Embeddings           │  │ Results              │
│ data/embeddings/     │  │ experiments/         │
└──────────┬───────────┘  └──────────┬───────────┘
           │                         │
           └──────────┬──────────────┘
                      ▼
           ┌──────────────────────┐
           │ S3 Sync               │
           │ s3://games-collections│
           └──────────────────────┘
```

## Quick Reference

### Training
```bash
# Local
just train-local

# AWS
just train-aws <instance>

# With RunCtl
just train-multigame-local
```

### Evaluation
```bash
# All games
just evaluate-all-games

# Comprehensive
just evaluate-final
```

### S3 Sync
```bash
# Full sync
just sync-s3

# Specific directory
just sync-s3-dir data/processed
```

## Next Steps

1. ✅ Pipeline reviewed and documented
2. ⏳ Consider migrating scripts to use PATHS (optional)
3. ⏳ Create data dependency graph
4. ⏳ Set up automated S3 sync on data changes
