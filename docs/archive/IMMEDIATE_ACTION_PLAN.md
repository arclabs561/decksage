# Immediate Action Plan - Critical Fixes

**Date**: 2025-01-27
**Status**: 🔴 **URGENT** - Broken systems blocking progress

---

## Critical Findings Summary

1. ❌ **Fusion worse than baseline** (0.088 vs 0.089)
2. ❌ **LLM Judge broken** (JSON parsing failures)
3. ❌ **No embeddings trained** (empty directory)
4. ❌ **No signals computed** (missing directory)
5. ⚠️ **35+ experiments, 71% made things worse**

---

## Immediate Actions (Today)

### ✅ Task 1: Fixed LLM Judge Error Handling
**Status**: ✅ **COMPLETE**

**Changes Made**:
- Added robust error handling and validation
- Added retry logic (max 2 retries)
- Added result structure validation
- Added relevance score validation
- Improved error messages

**File**: `src/ml/annotation/llm_judge_batch.py`

**Next**: Test with actual queries to verify fixes

### 🔴 Task 2: Train Embeddings (NEXT)
**Priority**: CRITICAL
**Time**: 1-2 hours
**Action**:
```bash
cd src/ml
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input ../../data/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128 \
  --workers 8
```

**Expected Output**: `data/embeddings/magic_128d_pecanpy.wv`

### 🔴 Task 3: Compute All Signals (NEXT)
**Priority**: CRITICAL
**Time**: 2-3 hours
**Action**:
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

**Expected Outputs**:
- `experiments/signals/sideboard_cooccurrence.json`
- `experiments/signals/temporal_cooccurrence.json`
- `experiments/signals/archetype_staples.json`
- `experiments/signals/archetype_cooccurrence.json`
- `experiments/signals/format_cooccurrence.json`
- `experiments/signals/cross_format_patterns.json`

### 🔴 Task 4: Measure Individual Signal Performance
**Priority**: HIGH
**Time**: 2 hours
**Action**: Create script to measure P@10 for:
- Jaccard only
- Functional only
- Embed only (after training)
- Compare to fusion (0.088)

**Purpose**: Understand why fusion is worse than baseline

### 🔴 Task 5: Fix Fusion Weights
**Priority**: HIGH
**Time**: 1 hour
**Action**: After Task 4, re-optimize weights based on individual signal performance

---

## This Week

### Task 6: Test LLM Judge Fixes
- Run on 3 test queries
- Verify JSON parsing works
- Check error handling

### Task 7: Train GNN Models
- After embeddings exist
- Run `train_gnn.py`
- Validate outputs

### Task 8: Expand Test Sets
- Use fixed LLM judge
- Generate 50+ queries per game
- Human review subset

---

## Success Criteria

### Immediate (Today)
- ✅ LLM Judge error handling improved
- 🔴 Embeddings trained
- 🔴 Signals computed
- 🔴 Individual signal performance measured

### This Week
- Fusion P@10 > 0.089 (beat baseline)
- All 9 signals operational
- Test sets expanded to 50+ queries per game

---

**Status**: ✅ **LLM JUDGE FIXED** - Ready for testing and next critical tasks!
