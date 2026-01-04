# Deep Structure Analysis - January 2025

## Critical Findings

### 1. Path Inconsistencies

**Problem**: Many scripts use hardcoded paths instead of `PATHS` abstraction.

**Examples**:
- `scripts/automation/daily_update.sh`: `data/graphs/incremental_graph.json` (hardcoded)
- `scripts/backfill_metadata.py`: `data/processed/decks_all_enhanced.jsonl` (hardcoded)
- Many scripts use `experiments/test_set_canonical_*.json` instead of unified versions

**Impact**:
- 164 files directly reference top-level paths
- Hardcoded paths break if structure changes
- Inconsistent test set usage (canonical vs unified)

**Recommendation**:
- Gradually migrate to `PATHS` abstraction
- Create migration script for test set paths (already exists: `scripts/test_sets/update_all_test_set_paths.sh`)

### 2. Script Organization

**Current Structure**:
- 145 total scripts (85 sh, 58 py)
- Subdirectories: `automation/`, `data_processing/`, `evaluation/`, `training/`, `test_sets/`, `annotations/`
- Many scripts at top-level of `scripts/` directory

**Issues**:
- Top-level scripts could be better organized
- Some scripts might be duplicates or variants
- No clear categorization for top-level scripts

**Recommendation**:
- Audit top-level scripts, move to appropriate subdirectories
- Document script categories and purposes
- Consider consolidating similar scripts

### 3. Test Set Migration

**Status**: Migration from `test_set_canonical_*.json` to `test_set_unified_*.json` is incomplete.

**Evidence**:
- Migration script exists: `scripts/test_sets/update_all_test_set_paths.sh`
- Some scripts still reference canonical versions
- `scripts/automation/daily_update.sh` uses `test_set_canonical_magic.json`

**Recommendation**:
- Run migration script to update all references
- Update automation scripts to use unified test sets
- Document which test sets are canonical vs unified

### 4. Go Embed Assets Issue

**Problem**: Go code embeds `assets/schema.graphql` but we moved `assets/` to `docs/assets/`.

**Location**: `src/backend/games/magic/store/store.go:11`
```go
//go:embed assets
var assets embed.FS
```

**Current**: Schema is at `src/backend/games/magic/store/assets/schema.graphql` (not affected)

**Status**: ✅ Actually OK - Go embed is relative to package, not project root

### 5. Legacy/Deprecated Code

**Found**: 29 matches for "deprecated", "legacy", "unused", "obsolete" in `src/ml/`

**Examples**:
- `src/ml/scripts/train_with_aws.py` - marked as deprecated
- `src/ml/api/api.py` - has legacy globals for backward compatibility
- `src/ml/similarity/fusion.py` - references legacy text embedder

**Recommendation**:
- Document which files are truly deprecated vs actively used
- Create deprecation timeline for removal
- Update imports to avoid deprecated modules

### 6. Import Patterns

**Inconsistency**: Scripts use different import patterns:
- `from ml.` (assumes installed package)
- `from src.ml.` (assumes src in path)
- Direct sys.path manipulation

**Recommendation**:
- Standardize on one pattern (prefer `from src.ml.` with sys.path setup)
- Document import patterns in contributing guide

## Recommendations Summary

### High Priority
1. ✅ **Complete test set migration** - Update all scripts to use unified test sets
2. ✅ **Migrate hardcoded paths** - Gradually move to `PATHS` abstraction
3. ✅ **Organize top-level scripts** - Move to appropriate subdirectories

### Medium Priority
4. ⚠️ **Document deprecated code** - Create deprecation guide
5. ⚠️ **Standardize imports** - Choose one pattern and document it
6. ⚠️ **Script consolidation** - Identify and merge duplicate scripts

### Low Priority
7. 📝 **Script documentation** - Add purpose/usage to each script
8. 📝 **Category organization** - Better subdirectory structure

## Metrics

- **Scripts**: 145 total (85 shell, 58 Python)
- **Hardcoded paths**: ~50+ instances in scripts
- **Test set references**: Mix of canonical/unified (migration incomplete)
- **Legacy code**: 29 references to deprecated/legacy
- **Import patterns**: 3 different patterns in use


## Additional Critical Findings

### 7. Script Consolidation Opportunities

**Monitoring Scripts** (8 similar scripts):
- `monitor_completion.py` - Monitors training/test sets until completion
- `monitor_comprehensive.py` - Comprehensive monitoring of all tasks
- `monitor_progress.py` - Monitors active tasks
- `monitor_quick.py` - Quick status check
- `monitor_until_completion.py` - Comprehensive monitoring until completion
- `monitor_training_unified.py` - Unified training monitoring
- `monitor_full_pipeline.sh` - Full pipeline monitoring
- `monitor_runctl_unified.sh` - Runctl unified monitoring

**Recommendation**: Consolidate into 2-3 scripts:
- `scripts/monitoring/quick_status.py` - Quick checks
- `scripts/monitoring/comprehensive.py` - Full monitoring
- `scripts/monitoring/pipeline.sh` - Pipeline-specific

### 8. Missing PATHS Entries

**Common paths not in PATHS**:
- `data/processed/card_attributes_enriched.csv` (3+ hardcoded references)
- `experiments/substitution_pairs_*.json` (multiple variants)
- `experiments/hyperparameter_results.json` (multiple references)
- `experiments/annotations_llm/` (directory)
- `annotations/` (top-level directory)

**Recommendation**: Add to PATHS:
```python
# In paths.py
CARD_ATTRIBUTES = PROCESSED_DIR / "card_attributes_enriched.csv"
ANNOTATIONS_DIR = PROJECT_ROOT / "annotations"
ANNOTATIONS_LLM_DIR = EXPERIMENTS_DIR / "annotations_llm"
SUBSTITUTION_PAIRS_COMBINED = EXPERIMENTS_DIR / "substitution_pairs_combined.json"
```

### 9. Test Set Migration Status

**Still using canonical** (found 15+ files):
- `scripts/automation/daily_update.sh` - Line 55
- `scripts/monitor_full_pipeline.sh` - Line 101
- `scripts/run_hybrid_complete.sh` - Line 59
- `scripts/runctl_labeling.sh` - Uses canonical
- `scripts/dataset_health_check.py` - Checks canonical versions

**Migration script exists**: `scripts/test_sets/update_all_test_set_paths.sh`
**Status**: ⚠️ Not fully applied

**Action**: Run migration script, update automation scripts manually

### 10. Common Experiment Files Pattern

**Frequently referenced experiment files**:
- `experiments/substitution_pairs_*.json` (6+ variants)
- `experiments/hyperparameter_results.json` (5+ references)
- `experiments/hybrid_evaluation_results.json` (4+ references)
- `experiments/test_set_expanded_*.json` (legacy, should use unified)

**Recommendation**:
- Add common experiment files to PATHS
- Document which files are canonical vs legacy
- Create migration guide for experiment file paths


## Action Items Summary

### Immediate Actions (High Priority)

1. **✅ COMPLETED**: Added missing PATHS entries
   - `PATHS.annotations` - annotations directory
   - `PATHS.annotations_llm` - LLM annotations directory
   - `PATHS.card_attributes` - card attributes CSV
   - `PATHS.substitution_pairs_combined` - combined substitution pairs
   - `PATHS.substitution_pairs_from_llm` - LLM substitution pairs
   - `PATHS.hyperparameter_results` - hyperparameter results
   - `PATHS.hybrid_evaluation_results` - hybrid evaluation results

2. **TODO**: Complete test set migration
   - Run: `scripts/test_sets/update_all_test_set_paths.sh`
   - Manually update shell scripts (sed doesn't work well on .sh files)
   - Update: `scripts/automation/daily_update.sh` line 55
   - Update: `scripts/monitor_full_pipeline.sh` line 101
   - Update: `scripts/run_hybrid_complete.sh` line 59

3. **TODO**: Migrate hardcoded paths to PATHS
   - `card_attributes_enriched.csv` (23 references) → `PATHS.card_attributes`
   - `substitution_pairs_*.json` (9 references) → `PATHS.substitution_pairs_*`
   - `annotations_llm/` (6 references) → `PATHS.annotations_llm`

### Medium Priority

4. **TODO**: Consolidate monitoring scripts
   - 12 monitoring scripts → consolidate to 3-4
   - Create `scripts/monitoring/` subdirectory
   - Keep: quick_status, comprehensive, pipeline

5. **TODO**: Organize top-level scripts
   - 79 scripts at top-level of `scripts/`
   - Move to appropriate subdirectories:
     - `scripts/monitoring/` - monitoring scripts
     - `scripts/validation/` - validation/verification scripts
     - `scripts/analysis/` - analysis/reporting scripts

6. **TODO**: Document deprecated code
   - Create `docs/DEPRECATED.md` listing deprecated files
   - Add deprecation timeline
   - Update imports to avoid deprecated modules

### Low Priority

7. **TODO**: Standardize import patterns
   - Choose one pattern (prefer `from src.ml.` with sys.path setup)
   - Document in contributing guide
   - Gradually migrate existing scripts

8. **TODO**: Script documentation
   - Add purpose/usage docstrings to all scripts
   - Create `scripts/README.md` with categorization

## Metrics Summary

- **Total scripts**: 145 (79 top-level, 66 in subdirs)
- **Monitoring scripts**: 12 (should be 3-4)
- **Validation scripts**: 16
- **Hardcoded paths**: 50+ instances
- **Test set references**: 527 (mix of canonical/unified)
- **Legacy code references**: 29
- **Missing PATHS entries**: ✅ Fixed (7 added)

## Next Steps

1. Run test set migration script
2. Update automation scripts to use unified test sets
3. Gradually migrate hardcoded paths to PATHS
4. Consider script consolidation (monitoring, validation)
5. Document deprecated code


## Additional Quality Issues

### 11. Script Error Handling Inconsistency

**Bash Scripts**:
- Some use `set -euo pipefail` (strict, recommended)
- Some use `set -e` (basic, missing `-uo pipefail`)
- Missing error handling in some scripts

**Recommendation**:
- Standardize on `set -euo pipefail` for all bash scripts
- Add error handling to scripts missing it
- Document error handling standards

### 12. Python Path Setup Patterns

**Inconsistency**: Multiple patterns for setting up Python paths:
- `sys.path.insert(0, str(script_dir.parent.parent / "src"))`
- `sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))`
- Direct `from ml.` imports (assumes installed package)

**Recommendation**:
- Create shared utility: `scripts/_common.py` with `setup_python_path()`
- Standardize on one pattern
- Document in contributing guide

### 13. Project Root Detection

**Pattern**: Many scripts detect project root differently:
- `Path(__file__).parent.parent.parent`
- `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`
- Looking for markers (pyproject.toml, etc.)

**Recommendation**:
- Use PATHS.PROJECT_ROOT (already exists in paths.py)
- Create shared bash function: `get_project_root()`
- Standardize project root detection

### 14. Script File Organization

**Current**: 79 scripts at top-level of `scripts/`
**Subdirectories**: automation/, data_processing/, evaluation/, training/, test_sets/, annotations/

**Missing categories**:
- `scripts/monitoring/` - monitoring scripts (12 scripts)
- `scripts/validation/` - validation/verification (16 scripts)
- `scripts/analysis/` - analysis/reporting scripts
- `scripts/utils/` - utility/helper scripts

**Recommendation**: Create missing subdirectories and move scripts
