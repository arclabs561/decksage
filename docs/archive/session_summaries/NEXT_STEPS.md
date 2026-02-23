# Next Steps - Architecture Refinement

**Last Updated**: 2026-01-07
**Status**: Critical tasks completed, ready for next phase

## Completed ✅

1. ✅ CI Failures Fixed (Go version, test imports)
2. ✅ safe_write Adoption Increased (37 → 39+ files)
3. ✅ Test Set Expansion Plan Created
4. ✅ API State Management Documented
5. ✅ Signal Availability Logging Enhanced

## Recommended Next Steps

### HIGH PRIORITY

#### 1. Test Set Expansion (refine-6)
**Goal**: Expand test sets to 100+ queries per game for statistical confidence

**Tasks**:
- [ ] Pokemon: 58 → 100+ queries (need 42+)
  - Generate 50+ candidate queries using LLM
  - Human review and select best 40-50
  - Annotate relevance labels
  - Merge into `experiments/test_set_unified_pokemon.json`
- [ ] Yugioh: 58 → 100+ queries (need 42+)
  - Same process as Pokemon
- [ ] Riftbound: 4 → 100+ queries (need 96+)
  - More comprehensive expansion needed
  - Focus on functional roles, archetype staples

**Estimated Time**: 4-5 hours total
**Priority**: High (improves evaluation quality)

#### 2. Continue safe_write Adoption
**Goal**: Reach 50+ files using safe_write

**Current**: 39+ files
**Target**: 50+ files
**Remaining**: ~11+ files

**Tasks**:
- [ ] Run search for remaining direct writes: `rg -t py "\.to_csv\(|json\.dump\(|open\(.*[\"']w" scripts/`
- [ ] Review each file and add safe_write
- [ ] Verify lineage orders are correct
- [ ] Update adoption metrics

**Estimated Time**: 1-2 hours
**Priority**: High (architectural consistency)

### MEDIUM PRIORITY

#### 3. Fix Test Functionality
**Goal**: Restore full test functionality

**Current Issues**:
- `QueryCache` class not available in `evaluation_registry.py`
- `scripts.deep_analysis` module not found

**Options**:
- Option A: Implement missing classes/modules
- Option B: Remove test dependencies on missing code
- Option C: Skip tests that depend on missing code (current approach)

**Estimated Time**: 1-2 hours
**Priority**: Medium (tests can run but some functionality stubbed)

#### 4. Review Remaining Hardcoded Paths
**Goal**: Ensure all paths use PATHS utility

**Tasks**:
- [ ] Run `check_hardcoded_paths.py` script
- [ ] Review and fix any remaining instances
- [ ] Verify pre-commit hook catches new violations

**Estimated Time**: 30 minutes
**Priority**: Medium (consistency improvement)

### LOW PRIORITY

#### 5. Expand Test Coverage
- Add more lineage validation edge cases
- Add schema validation edge cases
- Test concurrent safe_write usage

#### 6. Documentation Improvements
- Document signal contribution measurement approach
- Update architecture docs with latest changes
- Create migration guide for safe_write adoption

## Metrics to Track

- **safe_write adoption**: 39+ → 50+ files
- **Test set sizes**: Pokemon/Yugioh 58 → 100+, Riftbound 4 → 100+
- **CI pass rate**: Monitor after fixes
- **Hardcoded paths**: Should be 0 (enforced by pre-commit)

## Decision Points

1. **QueryCache**: Should we implement it or remove test dependencies?
2. **Test set expansion**: Manual annotation vs LLM-assisted vs hybrid?
3. **safe_write strictness**: Continue with `strict=False` or move to `strict=True`?

## Notes

- Test set expansion is the highest-impact remaining task
- safe_write adoption is progressing well (39+ files)
- CI is now stable after Go version fix
- All critical architectural patterns are in place
