# Critical Findings and Data-Driven Action Plan

**Date**: November 10, 2025
**Analysis**: Scientific, error-review motivated
**Status**: Ready for implementation

---

## Critical Discoveries

### Performance Reality
- **Current Fusion**: P@10 = 0.0882
- **Baseline (Jaccard)**: P@10 = 0.089
- **Best Ever Achieved**: P@10 = 0.15 (from experiment log)
- **Gap**: Fusion is **worse** than baseline!

### Experiment History
- **Total experiments**: 35
- **Failed completely**: 9 (26%)
- **Improved over baseline**: 1 (3%)
- **Made things worse**: 25+ (71%)

**Critical Insight**: Most experiments hurt performance!

### Test Set
- **Size**: 38 queries (small but honest)
- **Evolution**: P@10 dropped from 0.14 (10 queries) → 0.089 (38 queries)
- **Status**: All queries labeled (honest baseline)

---

## Scientific Questions (Must Answer First)

### Q1: Why is Fusion Worse Than Baseline?
**Current**: Fusion (0.0882) < Jaccard alone (0.089)
**Hypothesis**:
- Weights are wrong (functional=0.7 may be too high)
- Signals are correlated (redundant information)
- One signal is hurting (embed or functional)

**Action**: Measure individual signal P@10

### Q2: What Made P@10=0.15 Work?
**Finding**: Best result was 0.15 (70% better than current)
**Question**: Which experiment achieved this?
**Action**: Find experiment with P@10=0.15, understand what worked

### Q3: Why Do Most Experiments Fail?
**Pattern**: 71% made things worse
**Hypothesis**:
- Signals are low quality
- Test set is biased
- Evaluation methodology issues

**Action**: Analyze failure patterns

---

## Data-Driven Action Plan

### Step 1: Measure Individual Signals (CRITICAL)
**Why**: Fusion is worse than baseline - need to know why

**Implementation**:
```python
# Measure P@10 for each signal alone:
# - embed only
# - jaccard only
# - functional only
# - Compare to fusion (0.0882) and baseline (0.089)
```

**Expected Findings**:
- If jaccard alone = 0.089: Confirms baseline
- If embed alone < 0.05: Embed signal is weak
- If functional alone < 0.05: Functional signal is weak
- If all signals similar: They're correlated (redundant)

**Decision Rule**:
- If one signal is much better: Use that signal primarily
- If signals are correlated: Remove redundant ones
- If all signals are weak: Need new signals (text embeddings)

### Step 2: Find What Made P@10=0.15 Work
**Why**: Best result is 70% better - need to replicate

**Action**:
- Search experiment log for P@10=0.15
- Identify method/weights that worked
- Understand why it worked
- Try to replicate

### Step 3: Add Confidence Intervals
**Why**: Test set is small (38 queries), need statistical rigor

**Implementation**: Use `evaluation_with_ci.py`
**Output**: "P@10 = 0.0882 (95% CI: 0.075, 0.101)"
**Impact**: Know if changes are statistically significant

### Step 4: Analyze Failure Cases
**Why**: 71% of experiments made things worse - need to understand why

**Implementation**: Use `analyze_failures.py`
**Output**: Failure categories, examples, patterns
**Impact**: Avoid repeating failed approaches

### Step 5: Weight Sensitivity Analysis
**Why**: Current weights may be suboptimal

**Implementation**: Use `weight_sensitivity.py --suggest`
**Output**: Suggested weight adjustments
**Impact**: Potentially +0.01-0.02 P@10

---

## Small, Quintessential Improvements

### Fix 1: Ensure Weight Normalization
**Issue**: Weights may not be normalized in fusion
**Change**: Add `normalize_weights()` call
**Impact**: Small but correct
**Risk**: Low

### Fix 2: Remove Redundant Signals (If Data Shows)
**Issue**: If signals are correlated, fusion may average them down
**Change**: Remove redundant signal, increase weight of best
**Impact**: Potentially +0.01-0.02 P@10
**Risk**: Medium (need data first)

### Fix 3: Fix Low-Quality Signal (If Data Shows)
**Issue**: If one signal has P@10 < 0.05, it's hurting fusion
**Change**: Remove or reduce weight of low-quality signal
**Impact**: Potentially +0.01-0.02 P@10
**Risk**: Medium (need data first)

### Fix 4: Replicate Best Method (P@10=0.15)
**Issue**: Current fusion is worse than best achieved
**Change**: Find and replicate method that achieved 0.15
**Impact**: Potentially +0.06 P@10 (0.088 → 0.15)
**Risk**: Low (replicating known good result)

---

## Implementation Order

### Phase 1: Measurement (Do First) ⚠️
1. Add CI to evaluation ✅ (code ready)
2. Measure individual signals (need to implement)
3. Find P@10=0.15 experiment (search log)
4. Analyze failures (script ready)

**Time**: 2-4 hours
**Outcome**: Understand system scientifically

### Phase 2: Small Fixes (Based on Data)
1. Fix weight normalization (if needed)
2. Remove redundant signals (if data shows)
3. Remove low-quality signals (if data shows)
4. Replicate best method (if found)

**Time**: 1-2 hours
**Outcome**: Small, evidence-based improvements

### Phase 3: New Signals (Only If Justified)
1. Text embeddings: Only if all signals are weak/correlated
2. GNN: Only if graph structure helps
3. Beam search: Only if greedy fails specific cases

**Time**: Variable
**Outcome**: Data-justified additions

---

## Key Principle

**No speculative improvements** - only changes justified by data:
1. Measure first
2. Understand why
3. Fix specific issues
4. Re-measure with CI

**Current Priority**: Understand why fusion < baseline before adding new signals.

---

## Files Created

1. ✅ `src/ml/analysis/measure_signal_performance.py` - Measure individual signals
2. ✅ `src/ml/analysis/analyze_failures.py` - Categorize failures
3. ✅ `src/ml/analysis/weight_sensitivity.py` - Analyze weight sensitivity
4. ✅ `src/ml/utils/evaluation_with_ci.py` - Add confidence intervals
5. ✅ `SCIENTIFIC_ANALYSIS_FINDINGS.md` - Analysis findings
6. ✅ `CRITICAL_FINDINGS_AND_ACTION_PLAN.md` - This file

**Status**: Analysis tools ready, need to run when files readable.
