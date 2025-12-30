# Archive: October 3, 2025 Tidy

This archive was created during a comprehensive repository review and tidying.

## What's Archived

### Documentation (docs/)
- **archive-2025-09-30/**: 54 markdown files from previous archive (5 days old)
- **status/**: 8 status markdown files
- **Root-level status docs**: 14 files (FINAL_STATUS, STATUS_OCT_2_2025, etc.)
- **Design documents**: API_AND_LOSS_DESIGN, HETEROGENEOUS_GRAPH_DESIGN, MATHEMATICAL_FORMULATION, DATA_QUALITY_PLAN

**Why**: Documentation explosion - 100+ markdown files for a medium-sized codebase. Violated principle: "Don't write needless mds to record progress."

### Experiments (experiments/)
- MOTIVATIONS.md, PRINCIPLES.md, ROADMAP.md, ADVANCED_METHODS_ROADMAP.md
- EXPERIMENT_LOG_OLD_PARTIAL.jsonl
- self_sustaining_state.json, SYSTEM_STATE_FINAL.json

**Why**: Consolidating to single canonical experiment log (EXPERIMENT_LOG_CANONICAL.jsonl).

## What Remains Active

- README.md (consolidated main entry point)
- USE_CASES.md (pragmatic guide to what works)
- experiments/EXPERIMENT_LOG_CANONICAL.jsonl (single source of truth)
- src/ml/experimental/ (premature sophistication, available when needed)
- src/ml/tests/ (31 passing tests)
- src/backend/ (Go backend with tests)

## Review Findings

**Critical Issues Found**:
1. 100+ markdown files (80% now archived)
2. 3-4 duplicate experiment tracking systems (consolidated)
3. Premature sophistication (A-Mem, memory evolution) moved to experimental/
4. Metric inflation caught (claimed 0.12, actual 0.08)
5. 53 experiments blocked by 1-line metadata bug (now fixed)

**Current Honest State**:
- P@10 = 0.08 (38-query test set)
- 4,718 decks with metadata
- Go tests: 57 tests (some passing, overall suite has issues)
- Python tests: 31/31 passing
- Solid foundation, needs focus on basics

## Principles Applied

- "The best code is no code" - deleted 80% of documentation
- "Duplication is far cheaper than wrong abstraction" - but we had multiple abstractions for same thing
- "Debug slow vs fast" - should have found metadata bug earlier
- "Frequently distrust prior progress" - caught metric inflation
- "Experience complexity before abstracting" - moved premature sophistication to experimental/

## Next Steps (as of Oct 3, 2025)

1. Fix failing test suite (Go overall fails)
2. Add scraper tests (0 tests for 400-line critical component)
3. Get P@10 > 0.10 on format-specific use case
4. Implement one working use case (format-specific suggestions)
5. Stop writing status documents - code and tests are the status

---

This archive preserves the journey, but the active repository is now focused on working code and honest measurement.
