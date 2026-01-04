# Deep Analysis: Comprehensive Evaluation & Modeling Review

**Date**: 2025-01-27
**Status**: 🔍 **CRITICAL FINDINGS** - Action Required Immediately

---

## Executive Summary

After deep analysis of evaluation results, experiment logs, test sets, and implementation details, **critical issues** have been identified that explain why performance is stuck at P@10=0.088:

1. ❌ **Fusion is WORSE than baseline** (0.088 vs 0.089)
2. ❌ **LLM Judge system has JSON parsing failures**
3. ❌ **No trained models exist** (embeddings directory empty)
4. ❌ **Signals not computed** (signals directory doesn't exist)
5. ⚠️ **35+ experiments, 71% made things worse**
6. ⚠️ **Test sets: 38 MTG (good!), but 0 YGO, 0.02 Pokemon**

---

## 1. Performance Reality Check

### Current Performance

| Metric | Value | Source |
|--------|-------|--------|
| **Fusion P@10** | **0.088** | `fusion_grid_search_latest.json` |
| **Baseline Jaccard** | **0.089** | `CURRENT_BEST_magic.json` |
| **Best Ever** | **0.15** | Experiment log (exp_025: format-specific) |
| **Cross-Game Overall** | **0.076** | `cross_game_metrics.json` |

**Critical Finding**: **Fusion (0.088) < Baseline (0.089)** - We're making things worse!

### Cross-Game Performance

| Game | P@10 | Queries | Status |
|------|------|---------|--------|
| **Magic** | 0.084 | 38 | ✅ Good coverage |
| **Yu-Gi-Oh** | **0.000** | 13 | ❌ Complete failure |
| **Pokemon** | **0.020** | 10 | ❌ Near failure |
| **Overall** | 0.076 | 61 | ⚠️ Poor |

**Critical Finding**: Non-MTG games are failing completely!

---

## 2. Test Set Analysis

### Actual Test Set Sizes

| Game | Queries | Status | Need |
|------|---------|--------|------|
| **Magic** | **38** | ✅ Better than expected | 50-100 |
| **Pokemon** | 10 | ⚠️ Small | 50-100 |
| **Yu-Gi-Oh** | 13 | ⚠️ Small | 50-100 |

**Finding**: Magic test set is actually **38 queries** (not 5 as some docs said). Still needs expansion but better than expected.

### Test Set Quality

**Magic Test Set** (`test_set_canonical_magic.json`):
- ✅ Well-structured (5 relevance levels)
- ✅ Diverse queries (38 cards: spells, creatures, lands, artifacts)
- ✅ Good coverage (Lightning Bolt, Brainstorm, Sol Ring, etc.)
- ⚠️ Still needs expansion to 50-100 for statistical power

**Pokemon/Yu-Gi-Oh**: Need significant expansion

---

## 3. Experiment History Analysis

### Experiment Log Summary

**Total Experiments**: 35+ (from `EXPERIMENT_LOG_CANONICAL.jsonl`)

**Success Rate**:
- ✅ **Improved**: 1 experiment (exp_025: format-specific, P@10=0.15)
- ⚠️ **Worse**: 25+ experiments (71%)
- ❌ **Failed**: 9 experiments (26%)

**Key Failures**:
1. **exp_036**: Metadata extraction - files exist but empty
2. **exp_033-035**: Frequency-based methods - all worse than baseline
3. **exp_028**: Archetype-weighted - failed (P@10=0.0)
4. **exp_022**: Node2Vec on 39K decks - P@10=0.0625 (worse!)

**Key Learnings** (from experiment log):
- "More data can hurt if graph is noisy" (exp_003)
- "Metadata extraction consistently fails" (exp_036)
- "Don't let perfect be enemy of good" (exp_030)
- "Co-occurrence has fundamental limits" (from analysis)

**Critical Insight**: Most experiments made things worse because:
1. Signals are correlated (redundant)
2. Some signals are low quality
3. Test set may be biased
4. Metadata extraction infrastructure broken

---

## 4. LLM Judge System Analysis

### Current Implementation

**File**: `src/ml/annotation/llm_judge_batch.py`

**Status**: ⚠️ **HAS BUGS**

**Issues Found**:
1. **JSON Parsing Failures**: `llm_judge_report.json` shows:
   ```json
   "analysis": "LLM evaluation failed: Expecting value: line 1 column 1 (char 0)"
   ```
   - All 3 queries failed with JSON parsing errors
   - No successful evaluations in report

2. **Single Judge Only**: Uses one LLM (Claude 3.5 Sonnet)
   - No multi-judge consensus
   - No IAA computation
   - No confidence calibration

3. **No Error Handling**: Failures are logged but not recovered

**What Works**:
- ✅ Agent creation (Pydantic AI)
- ✅ Batch processing structure
- ✅ Test set conversion format

**What's Broken**:
- ❌ JSON parsing (LLM response format issues)
- ❌ Error recovery
- ❌ Multi-judge support

---

## 5. Training Status Deep Dive

### Embeddings

**Status**: ❌ **NOT TRAINED**

**Evidence**:
- `data/embeddings/` directory is **empty**
- No `.wv` files found
- Experiment log mentions embeddings but files don't exist

**Impact**:
- Cannot use embedding signal in fusion
- All embedding-based methods will fail
- GNN cannot be trained (needs embeddings or graph)

### Signals

**Status**: ❌ **NOT COMPUTED**

**Evidence**:
- `experiments/signals/` directory **doesn't exist**
- No cached signal files:
  - No `sideboard_cooccurrence.json`
  - No `temporal_cooccurrence.json`
  - No `archetype_staples.json`
  - No `format_cooccurrence.json`
  - No `gnn_embeddings.json`

**Impact**:
- Cannot use 6 of 9 signals in fusion
- Only 3 signals available: embed (broken), jaccard, functional
- GNN signal missing
- Sideboard, temporal, archetype, format signals missing

### GNN Models

**Status**: ❌ **NOT TRAINED**

**Evidence**:
- Code exists (`src/ml/similarity/gnn_embeddings.py`)
- Training script exists (`src/ml/scripts/train_gnn.py`)
- No trained models or embeddings

**Impact**:
- GNN signal unavailable
- Missing one of 9 fusion signals

---

## 6. Modeling Design Deep Dive

### Current Fusion Architecture

**9 Signals Designed**:
1. Embedding (Node2Vec) - ❌ Not trained
2. Jaccard - ✅ Available
3. Functional tags - ✅ Available
4. Text embeddings - ⚠️ Unknown status
5. Sideboard co-occurrence - ❌ Not computed
6. Temporal trends - ❌ Not computed
7. GNN embeddings - ❌ Not trained
8. Archetype staples - ❌ Not computed
9. Format patterns - ❌ Not computed

**Actual Available Signals**: **3 of 9** (33%)

**Fusion Weights** (from `fusion_grid_search_latest.json`):
```json
{
  "embed": 0.1,
  "jaccard": 0.2,
  "functional": 0.7
}
```

**Problem**: Only 3 signals available, but weights optimized for 9 signals!

### Why Fusion is Worse Than Baseline

**Hypothesis**:
1. **Embed signal broken** (no embeddings trained) → weight=0.1 wasted
2. **Functional signal may be weak** (weight=0.7 too high)
3. **Jaccard alone (0.089) > Fusion (0.088)** suggests:
   - Embed signal (0.1 weight) is hurting
   - Functional signal (0.7 weight) is not helping enough

**Evidence**:
- Baseline Jaccard: 0.089
- Fusion (embed=0.1, jaccard=0.2, functional=0.7): 0.088
- Difference: -0.001 (fusion worse!)

**Conclusion**: Current fusion weights are suboptimal because:
1. Embed signal doesn't exist (weight wasted)
2. Functional signal may not be strong enough to justify 0.7 weight
3. Need to measure individual signal performance

---

## 7. Evaluation System Deep Dive

### What Exists

**✅ Implemented**:
- `evaluation_with_ci.py` - Bootstrap confidence intervals
- `ab_testing.py` - A/B testing framework
- `inter_annotator_agreement.py` - IAA metrics (just created)
- Basic metrics (P@K, nDCG, MRR)

**⚠️ Partially Implemented**:
- LLM-as-Judge (has JSON parsing bugs)
- Multi-judge consensus (not implemented)
- Test set expansion (scripts exist, not run)

**❌ Missing**:
- IAA integration into annotation pipeline
- Multi-judge LLM system
- Confidence calibration
- Test set expansion execution

### Statistical Rigor

**Current**:
- P@10 = 0.088 (no CI reported)
- n = 38 queries (Magic)
- No significance testing

**Needed**:
- Bootstrap CI: P@10 = 0.088 ± 0.015 (95% CI, n=38)
- Significance testing for model comparisons
- IAA > 0.75 for human annotations

---

## 8. Critical Action Items (Prioritized)

### 🔴 Priority 1: Fix Broken Systems (IMMEDIATE)

#### Task 1.1: Fix LLM Judge JSON Parsing
**File**: `src/ml/annotation/llm_judge_batch.py`
**Issue**: JSON parsing failures
**Fix**: Add better error handling, validate JSON structure, retry logic

#### Task 1.2: Train Embeddings
**Action**: Run embedding training
```bash
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input data/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128
```

#### Task 1.3: Compute All Signals
**Action**: Run signal computation
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

#### Task 1.4: Measure Individual Signal Performance
**Action**: Create script to measure P@10 for each signal alone
- Jaccard only
- Functional only
- Embed only (after training)
- Compare to fusion

### 🟡 Priority 2: Expand Evaluation (HIGH)

#### Task 2.1: Fix LLM Judge and Generate Test Sets
**Action**: Fix JSON parsing, then use LLM-as-Judge to expand test sets to 50+ queries per game

#### Task 2.2: Implement Multi-Judge System
**Action**: Create `multi_judge_llm.py` with consensus computation

#### Task 2.3: Integrate IAA
**Action**: Add IAA computation to annotation pipeline

### 🟢 Priority 3: Improve Modeling (MEDIUM)

#### Task 3.1: Optimize Fusion Weights
**Action**: After measuring individual signals, re-optimize weights

#### Task 3.2: Train GNN
**Action**: Train GNN models after embeddings exist

#### Task 3.3: Implement Node Similarity-Based Convolution
**Action**: Research-based improvement for GNN

---

## 9. Root Cause Analysis

### Why Performance is Stuck

**Primary Causes**:
1. **Missing Signals**: 6 of 9 signals not computed/trained
2. **Broken Signals**: Embed signal doesn't exist (weight wasted)
3. **Suboptimal Weights**: Optimized for 9 signals but only 3 available
4. **Infrastructure Issues**: Metadata extraction broken, LLM judge broken
5. **Test Set Limitations**: Non-MTG games failing (0.000, 0.020)

**Secondary Causes**:
1. **Experiment Quality**: 71% of experiments made things worse
2. **Signal Correlation**: Signals may be redundant
3. **Fundamental Limits**: Co-occurrence alone may have ceiling (papers show 0.42 with multi-modal)

### Why Most Experiments Failed

**Patterns**:
1. **Metadata Extraction**: Consistently fails (exp_036, exp_028, etc.)
2. **Frequency Methods**: Don't help (exp_033-035)
3. **Graph Structure**: Doesn't improve (exp_037)
4. **More Data**: Can hurt (exp_003, exp_018)

**Root Cause**:
- Infrastructure issues (metadata parsing)
- Signal quality issues (frequency, graph structure weak)
- Test set bias (may favor certain methods)

---

## 10. Success Metrics & Targets

### Immediate (Week 1)

- ✅ IAA system implemented
- 🔴 Fix LLM judge JSON parsing
- 🔴 Train embeddings
- 🔴 Compute all signals
- 🔴 Measure individual signal performance

### Short-term (Month 1)

- Expand test sets to 50+ queries per game
- Multi-judge LLM system operational
- IAA > 0.75 for human annotations
- Fusion P@10 > 0.10 (from 0.088)

### Long-term (Month 3)

- Test sets: 100+ queries per game
- All 9 signals operational
- Fusion P@10 > 0.15 (match best ever)
- Cross-game: YGO > 0.05, Pokemon > 0.10

---

## 11. Files Status Matrix

| Component | File | Status | Issue |
|-----------|------|--------|-------|
| **IAA System** | `inter_annotator_agreement.py` | ✅ Complete | None |
| **LLM Judge** | `llm_judge_batch.py` | ⚠️ Broken | JSON parsing |
| **Multi-Judge** | `multi_judge_llm.py` | ❌ Missing | Not created |
| **Embeddings** | `data/embeddings/*.wv` | ❌ Missing | Not trained |
| **Signals** | `experiments/signals/*.json` | ❌ Missing | Not computed |
| **GNN** | `experiments/signals/gnn_embeddings.json` | ❌ Missing | Not trained |
| **Test Sets** | `test_set_canonical_*.json` | ⚠️ Partial | Need expansion |
| **Evaluation** | `evaluation_with_ci.py` | ✅ Complete | None |
| **A/B Testing** | `ab_testing.py` | ✅ Complete | None |

---

## 12. Next Steps (Immediate)

### Today

1. **Fix LLM Judge** (2 hours)
   - Debug JSON parsing
   - Add error handling
   - Test on 3 queries

2. **Train Embeddings** (1 hour)
   - Run training script
   - Validate output
   - Test loading

3. **Compute Signals** (2 hours)
   - Run signal computation
   - Validate outputs
   - Check file sizes

### This Week

4. **Measure Individual Signals** (4 hours)
   - Create measurement script
   - Run on test set
   - Compare to fusion

5. **Fix Fusion Weights** (2 hours)
   - Re-optimize based on individual signal performance
   - Validate improvement

6. **Expand Test Sets** (8 hours)
   - Fix LLM judge first
   - Generate 50+ queries per game
   - Human review subset

---

**Status**: 🔴 **CRITICAL ISSUES IDENTIFIED** - Immediate action required on broken systems!
