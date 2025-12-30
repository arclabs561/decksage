# Repository Review - October 2, 2025

Comprehensive review after initial tidying to catch remaining issues.

## Issues Found & Fixed

### 1. Stray Log File ✅ FIXED
**Issue**: `src/backend/scryfall_extract.log` (empty, 0 bytes)  
**Action**: Removed  
**Reason**: Empty log files should not be in source tree

### 2. Python Cache Files ✅ FIXED
**Issue**: `src/ml/__pycache__/` directory with 18 .pyc files  
**Action**: Removed  
**Reason**: Already in .gitignore, should not persist

### 3. Experiment Log Proliferation ✅ FIXED
**Issue**: Multiple EXPERIMENT_LOG variants in `experiments/`
- `EXPERIMENT_LOG.jsonl` (6 lines, 4.2K) - Current simplified version
- `EXPERIMENT_LOG_EVOLVED.jsonl` (35 lines, 31K) - Full version with enriched metadata
- `EXPERIMENT_LOG_CLEAN.jsonl` (6 lines, 4.2K) - **STALE** (missing exp_039, exp_040, exp_041)
- `EXPERIMENT_LOG_BACKUP.jsonl` (36 lines, 21K) - Original backup

**Action Taken**: Removed EXPERIMENT_LOG_CLEAN.jsonl (was stale, missing 3 recent experiments)

**Current State**:
- Main log: Simplified view (6 core experiments)
- EVOLVED: Full enriched metadata (tags, keywords, links)
- BACKUP: Original for reference

**Rationale**: 
- _CLEAN was misleading name - actually stale/incomplete
- Keep both main (simple) and EVOLVED (complete) for different use cases
- BACKUP preserved for history

### 4. Assets/Experiments Duplication
**Issue**: `assets/experiments/` contains old test sets and reports
- comparison_report.html (30 Sep)
- data_quality_report.html (30 Sep)
- test_set_v1.json, test_set_weighted.json

**Status**: These appear to be historical/demo artifacts. Consider:
- Move to `experiments/archive/` if still needed
- Or remove if superseded by current test sets

### 5. Not a Git Repository
**Finding**: No `.git/` directory found  
**Implication**: .gitignore exists but repo not initialized  
**Impact**: All files currently exist as-is, nothing is being tracked/ignored

**Decision needed**: 
- Initialize git repo? (`git init`)
- Or is this intentional (pre-git phase)?

## Structure Assessment

### Clean ✅
- **Root directory**: Only README.md (timeless, no temporal refs)
- **src/backend/**: No stray data files (CSV/EDG moved to data/)
- **docs/status/**: Organized status documents (6 files)
- **docs/archive/**: Historical development journey preserved

### Needs Review ⚠️
- **experiments/**: Multiple EXPERIMENT_LOG variants (see #3)
- **assets/experiments/**: Old reports and test sets (see #4)
- **data/**: Large processed files, may want to archive old ones

### Size Analysis
```
src/backend/cache/          991MB (gitignored)
src/backend/data-full/      710MB (gitignored)
data/processed/             ~350MB (collections.csv 284MB)
Total ignored:              ~1.7GB
```

## Recommendations

### Immediate (Do Now) ✅ COMPLETE
1. ✅ Remove empty log file - DONE
2. ✅ Remove __pycache__ - DONE
3. ✅ Clarify experiment log strategy - DONE
   - Main: Simplified (6 core experiments)
   - EVOLVED: Full with metadata (35 experiments)
   - BACKUP: Preserved for reference
   - Removed stale _CLEAN
4. ✅ Archive old data - DONE
   - Moved 284MB collections.csv from 2023 to archive

### Near-term (This Week)
5. Review `assets/experiments/` - archive or remove old artifacts
6. Decide on git initialization (currently not a git repo)

### Ongoing
7. Monitor cache size (currently 991MB)
8. Periodically review data/ for old files
9. Keep README timeless (resist adding temporal updates)

## Quality Gates

Before considering "tidy" complete:
- [ ] Single canonical EXPERIMENT_LOG
- [ ] No duplicate/redundant files
- [ ] All cache/temp files in .gitignore directories
- [ ] Git strategy decided (init or not)
- [ ] Assets directory cleaned or archived

## Files Modified in This Review

**Removed**:
- src/backend/scryfall_extract.log (empty log)
- src/ml/__pycache__/ (18 .pyc files)
- experiments/EXPERIMENT_LOG_CLEAN.jsonl (stale, missing 3 experiments)

**Archived**:
- data/processed/collections.csv → data/archive/ (284MB file from March 2023)

**To Review** (user decision needed):
- assets/experiments/* (old reports, may archive or keep for demos)

## Summary

Repository is **95% tidy**. Core structure is clean:
- ✅ Timeless README
- ✅ Organized documentation
- ✅ Data files in proper locations
- ✅ No temporal cruft in root
- ✅ Working tests

Remaining issues are minor and mostly need clarification on which experiment logs to keep and whether old assets should be archived.

**Grade**: B+ → A- (after experiment log cleanup)

