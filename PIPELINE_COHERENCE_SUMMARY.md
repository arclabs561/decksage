# Pipeline Coherence - Executive Summary

## Status: ✅ COHERENT

The entire pipeline (S3, datasets, training, evaluation) is coherent and well-organized.

## Key Findings

### ✅ S3 Usage
- **Bucket**: `s3://games-collections` (consistent)
- **Structure**: Clear organization (processed/, embeddings/, experiments/, graphs/)
- **Sync**: Scripts updated to include new deck files

### ✅ Datasets
- **Training**: `pairs_large.csv` (7.5M pairs) - Primary
- **Decks**: `decks_all_final.jsonl` (69K decks) - **RECOMMENDED** for deck-based training
- **Test Sets**: Canonical sets available for all games
- **All files**: Present and documented

### ✅ Training Pipeline
- **Local**: Uses local paths
- **AWS**: Uses S3 paths consistently
- **RunCtl**: Proper S3 integration
- **Data flow**: Clear from canonical → export → enhance → train

### ✅ Evaluation Pipeline
- **Test sets**: Canonical (production) + Expanded (analysis)
- **Scripts**: 32 evaluation scripts available
- **Embeddings**: Production + 21 experimental

## Minor Issues (Non-Critical)

1. **Hardcoded paths**: 21 scripts use hardcoded paths instead of PATHS
   - **Impact**: Low (paths work, just not using centralized constants)
   - **Fix**: Optional migration to PATHS

2. **Test set naming**: Mix of canonical/expanded in scripts
   - **Impact**: Low (both work, just need to know which to use)
   - **Fix**: Document when to use which

## Recommendations

### Immediate (Done)
- ✅ Updated paths.py with new deck files
- ✅ Updated sync scripts
- ✅ Documented pipeline

### Optional (Nice to Have)
- Migrate scripts to use PATHS (low priority)
- Create data dependency graph
- Set up automated S3 sync

## Quick Reference

**Training Data:**
- Co-occurrence: `pairs_large.csv`
- Multi-game: `pairs_multi_game.csv` (MTG-only currently)
- Decks: `decks_all_final.jsonl` ✅

**Test Sets:**
- Production: `test_set_canonical_*.json`
- Analysis: `test_set_expanded_*.json`

**S3:**
- Bucket: `s3://games-collections`
- Sync: `just sync-s3`

## Conclusion

✅ **Pipeline is coherent and ready for use**
- All data flows are clear
- S3 usage is consistent
- Training and evaluation pipelines are well-defined
- Minor improvements are optional

