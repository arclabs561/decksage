# Architecture Refinement - Next Steps

## Completed ✅

1. **Architecture Enforcement Tooling**
   - Pre-commit hooks for hardcoded paths, lineage, schema validation
   - Validation scripts created and tested
   - Unit tests passing (14/14)
   - CI workflow working (3.4 minutes)
   - Merged to main branch

2. **Fixed Hardcoded Paths**
   - `src/ml/api/query_history.py`: Now uses `PATHS.data / "analytics"`
   - `src/ml/api/feedback.py`: Now uses `PATHS.data / "annotations"`
   - `src/ml/utils/export_tools.py`: Now uses `PATHS.backend`

## Current Adoption Metrics

- **safe_write**: 35 files using it
- **validate_deck_record**: 17 files using it
- **DeckExport/DeckRecord**: 5 files using it
- **PATHS utility**: 667 files (excellent adoption)

## Priority Next Steps

### High Priority

1. **Increase safe_write Adoption**
   - Target: 50+ files using safe_write for data writes
   - Focus on: `scripts/data_processing/`, `scripts/training/`
   - Impact: Prevents accidental writes to Order 0 (immutable data)

2. **Increase Schema Validation Adoption**
   - Target: All deck loading code uses `validate_deck_record`
   - Focus on: `src/ml/utils/data_loading.py` (already has it, but ensure all callers use it)
   - Impact: Catches Go/Python integration issues early

3. **Fix Pre-existing CI Failures**
   - Go lint: Investigate and fix
   - Fast tests: Investigate and fix
   - Impact: Unblocks PR merges, improves code quality

### Medium Priority

4. **Document API State Management**
   - Document worker configuration requirements
   - Add examples for testing with different state
   - Impact: Helps with deployment and testing

5. **Add Signal Availability Logging**
   - Log which signals are loaded at API startup
   - Help diagnose fusion performance issues
   - Impact: Better observability

6. **Expand Test Sets**
   - Target: 100+ queries per game (currently 38 MTG, 10 Pokemon, 13 YGO)
   - Impact: Statistical confidence in evaluation metrics

### Low Priority

7. **Fix Remaining Hardcoded Paths**
   - Analysis scripts (relative paths acceptable)
   - Test files (acceptable)
   - Impact: Consistency, but lower risk

8. **Measure Signal Contributions**
   - Which signals are actually non-zero at runtime?
   - Which signals contribute to final similarity scores?
   - Impact: Better understanding of fusion performance

## Notes

- Architecture enforcement tooling is working correctly
- Most critical architectural patterns are in place
- Focus should shift to adoption and performance improvements
