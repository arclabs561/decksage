# DeckSage Quick Reference

Start here: `README.md`  
Deep analysis: `DEEP_REVIEW_TRIAGED_ACTIONS.md`

---

## Development Workflow

```bash
# Daily development
just sync          # Sync deps
just test-quick    # Quick test
just lint          # Check quality
just format        # Auto-format

# Full testing
just test          # All tests (activate venv, avoid uv collection hang)
just test-api      # API tests only

# ML Pipeline (legacy - use runctl commands for training)
just pipeline-train    # Train embeddings (legacy)
just serve             # Start API server
just pipeline-full     # Complete pipeline (export → train → tune, legacy)

# Enrichment
just enrich-mtg        # MTG functional tags (free)
just enrich-pokemon    # Pokemon functional tags (free)
just enrich-yugioh     # YGO functional tags (free)
```

Note: Use `just test` (not `uv run pytest`) - activates venv to avoid collection overhead.

---

## Current System State

Performance:
- P@10 = 0.088 ± ? (current, no confidence intervals)
- Target: P@10 = 0.20-0.25 (requires card text embeddings)
- Plateau: Co-occurrence alone maxes at ~0.08 (documented reality)

Data:
- 52,330 cards (MTG 35k, Pokemon 3k, YGO 14k)
- 56,521 tournament decks  
- 90% cross-game parity achieved

Test Coverage:
- 30+ test files
- 185+ test functions
- Property-based testing (Hypothesis)
- Nuances documented (`test_nuances.py`)

---

## Priority Next Steps (From Deep Review)

### Tier 0: Critical Path (Do First)
1. **Expand test set** → 100+ queries with confidence intervals (6-10h)
2. **Add deck quality validation** → measure if completion works (6-10h)
3. **Unified quality dashboard** → prevent silent degradation (4-6h)

### Tier 1: Break Performance Ceiling (Do Next)
1. **Card text embeddings** → biggest impact on P@10 (13-19h)
2. **A/B testing framework** → rigorous comparisons (6-8h)

### Tier 2: Technical Excellence (Lower Priority)
1. **Remove legacy globals** → cleaner code (2-3h)
2. **Centralize paths** → robustness (1-2h)
3. **Add type hints** → better DX (3-4h)

Total MVP: 16-26 hours (T0 items)  
Full product: 35-45 hours (T0 + T1.1 + T0.3)

---

## Key Files to Know

### Core Application
- `src/ml/api.py` (821 lines) - FastAPI server, fusion orchestration
- `src/ml/fusion.py` (421 lines) - Multi-signal fusion (weighted, RRF, CombMNZ, MMR)
- `src/ml/deck_completion.py` (409 lines) - Greedy deck completion algorithm

### Data & Validation
- `src/ml/validators/loader.py` (735 lines) - Robust data loading with 6-strategy game detection
- `src/ml/validators/models.py` (407 lines) - Pydantic models with format-specific rules
- `src/ml/validators/legality.py` (427 lines) - Ban list validation with caching

### Enrichment
- `src/ml/unified_enrichment_pipeline.py` - Orchestrates 5-dimension enrichment
- `src/ml/card_functional_tagger.py` (484 lines) - MTG 30+ tags
- `src/ml/llm_semantic_enricher.py` (427 lines) - LLM strategic analysis

### Evaluation
- `src/ml/utils/evaluation.py` - Standard metrics (P@K, nDCG, MRR)
- `src/ml/fusion_grid_search_runner.py` - Weight tuning
- `experiments/test_set_canonical_*.json` - Ground truth (38 MTG, 15 Pokemon, 20 YGO)

### Infrastructure
- `src/ml/utils/llm_cache.py` (144 lines) - 30-day TTL, 1GB limit, concurrent-safe
- `src/ml/utils/paths.py` - Centralized path configuration
- `justfile` - All workflow targets (dev, testing, training, data pipeline)
- `scripts/verify_training_status.py` - Training instance verification
- `scripts/analyze_idle_instances.py` - Idle instance analysis

---

## Known Limitations (Honest Assessment)

1. **P@10 = 0.08 plateau** - Co-occurrence alone can't exceed this (documented in `experimental/REALITY_FINDINGS.md`)
2. **Small test set** - 38 MTG queries insufficient for confident evaluation
3. **Naive completion** - Greedy algorithm with no deck quality objective
4. **No text signals** - Missing biggest performance lever
5. **Pytest collection slow** - Full suite hangs, individual files work (<2s)

All have documented workarounds or are acceptable for research code.

---

## Documentation Structure

```
Essential (6 files):
├── README.md                           # Start here
├── ENRICHMENT_QUICKSTART.md            # Enrichment quick start
├── COMMANDS.md                         # Command reference
├── QUICK_REFERENCE.md                  # This file
├── DEEP_REVIEW_TRIAGED_ACTIONS.md      # Strategic analysis
└── REVIEW_SUMMARY.md                   # Implementation summary

Historical:
└── archive/2025-10-06-ml-review/       # Session details
```

---

## Training on AWS

```bash
# Create training instance (defaults to g4dn.xlarge)
just train-aws-create

# Check training status (excludes personal infrastructure)
uv run --script scripts/verify_training_status.py

# Analyze idle instances
uv run --script scripts/analyze_idle_instances.py

# Monitor specific instance
just train-aws-monitor <instance-id>
```

Note: Training instances default to `g4dn.xlarge` (GPU-enabled). Personal infrastructure (gyarados, alakazam) is automatically excluded from training management scripts.

## Getting Help

If confused about, read this first:
- Build/sync issues → `REVIEW_SUMMARY.md` (fixes applied section)
- Test execution → `justfile` + this file
- Performance plateau → `experimental/REALITY_FINDINGS.md`
- Next steps → `DEEP_REVIEW_TRIAGED_ACTIONS.md`
- Architecture → `README.md` (architecture section)
- Training management → `README.md` (training section)

Common Issues:
- `uv run pytest` hangs → Use `just test` instead
- Import errors → Run `just sync`
- Test failures → Expected (some tests need embeddings loaded)

---

## Principles This System Follows

1. **Property-driven testing** - Hypothesis, invariant tests
2. **Be liberal in what you accept** - Validators handle messy data
3. **Caching pushed lower** - LLM cache, fusion weights cache
4. **Story-driven dev** - README explains why, not just what
5. **Honest baselines** - P@10 = 0.08 plateau documented
6. **Chesterton's fence** - Duplication kept when justified
7. **Tests as documentation** - `test_nuances.py` documents behaviors

---

## Quick Wins Available

If you have 1-2 hours and want immediate value:

1. **Fix hardcoded path** (1h) - T2.2 in deep review
2. **Add 10 more test queries** (2h) - Partial progress on T0.1
3. **Run quality validation** (30min) - Generate baseline report
4. **Profile one slow test** (1h) - `pytest --durations=10`

These are all low-risk, high-clarity improvements.
