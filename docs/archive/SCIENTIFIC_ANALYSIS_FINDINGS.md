# Scientific Analysis Findings

**Date**: November 10, 2025  
**Approach**: Data-driven, error-review motivated  
**Status**: Analysis in progress

---

## Critical Data Discovered

### Test Set Reality
- **Size**: 38 queries (not 100+ as hoped)
- **Evolution**: P@10 dropped from 0.14 (10 queries) → 0.089 (38 queries)
- **Implication**: Small sample size requires confidence intervals
- **Status**: "Honest baseline" - all queries labeled

### Current Performance
- **P@10**: 0.0882 (fusion with embed=0.1, jaccard=0.2, functional=0.7)
- **Baseline**: 0.089 (Jaccard with land filtering)
- **Gap**: Fusion is actually slightly worse than baseline!
- **Critical Finding**: Current fusion weights may be suboptimal

### Experiment History Analysis
From `EXPERIMENT_LOG_CANONICAL.jsonl`:
- **Total experiments**: 37+ (exp_033 to exp_037+ visible)
- **Failed attempts**: Multiple (metadata extraction, frequency, etc.)
- **Key failures**:
  - exp_033: Jaccard + Frequency (P@10=0.101) - worse than baseline
  - exp_034: Meta stats + land filter (P@10=0.099) - worse
  - exp_035: Weighted Jaccard (P@10=0.119) - worse than baseline 0.14
  - exp_036: Metadata extraction - **FAILED** (files exist but empty)
  - exp_037: Graph structure signals (P@10=0.118) - worse

**Critical Insight**: Many experiments made things worse, not better!

---

## Scientific Questions to Answer

### Question 1: Why is Fusion Worse Than Baseline?
**Hypothesis**: Weight combination is suboptimal
**Data Needed**: 
- Individual signal P@10 (embed, jaccard, functional alone)
- Weight sensitivity analysis
- Correlation between signals

**Action**: Measure individual signal performance

### Question 2: Why Did Previous Experiments Fail?
**Patterns Observed**:
- Metadata extraction consistently fails (exp_036 diagnosis)
- Frequency-based methods underperform
- Graph structure signals don't help

**Hypothesis**: 
- Signals may be correlated (redundant)
- Some signals may have low quality
- Test set may be biased

**Action**: Analyze failure cases and signal correlation

### Question 3: Is Test Set Size Sufficient?
**Current**: 38 queries
**Statistical Power**: 
- 95% CI width ≈ ±0.05 for P@10=0.09 with n=38
- Need n=100+ for ±0.02 CI width

**Action**: Add confidence intervals, consider expanding test set

---

## Evidence-Based Improvements (Small, Quintessential)

### Improvement 1: Add Confidence Intervals ✅
**Why**: 
- Test set is small (38 queries)
- Current P@10=0.0882 has no uncertainty
- Can't tell if 0.088 vs 0.089 is meaningful

**Change**: 
- Use `evaluation_with_ci.py` for all metrics
- Report: "P@10 = 0.0882 (95% CI: 0.075, 0.101)"

**Impact**: Statistical rigor, know if changes are significant
**Effort**: Small (already implemented)

### Improvement 2: Measure Individual Signal Performance
**Why**: 
- Fusion (0.0882) is worse than baseline (0.089)
- Need to know which signals help/hurt
- May find one signal is much better

**Change**: 
- Run `measure_signal_performance.py`
- Measure P@10 for embed, jaccard, functional alone
- Compare to fusion

**Impact**: Understand signal quality, optimize weights
**Effort**: Medium (need to implement similarity function imports)

### Improvement 3: Fix Weight Normalization
**Why**: 
- Current weights: embed=0.1, jaccard=0.2, functional=0.7 (sum=1.0)
- But fusion may not normalize properly
- Small normalization errors can hurt performance

**Change**: 
- Ensure weights sum to 1.0 in fusion code
- Use `normalize_weights()` from fusion_integration.py

**Impact**: Small but correct
**Effort**: Minimal (one-line fix when code readable)

### Improvement 4: Analyze Why Experiments Failed
**Why**: 
- Many experiments made things worse
- Need to understand failure modes
- Avoid repeating failed approaches

**Change**: 
- Run `analyze_failures.py` on test set
- Categorize failure types
- Identify systematic issues

**Impact**: Avoid wasted effort, focus on what works
**Effort**: Medium (need predictions or similarity function)

### Improvement 5: Weight Sensitivity Analysis
**Why**: 
- Current weights may be suboptimal
- Small adjustments might help
- Need to understand weight space

**Change**: 
- Run `weight_sensitivity.py` on grid search results
- Identify if current weights are in optimal region
- Suggest small adjustments

**Impact**: Potentially +0.01-0.02 P@10
**Effort**: Small (script ready, just need to run)

---

## Implementation Priority (Data-Driven)

### Phase 1: Measurement (Do First) ⚠️ CRITICAL
1. **Add confidence intervals** to current evaluation
2. **Measure individual signal P@10**
3. **Analyze failure cases** (why fusion < baseline)
4. **Weight sensitivity analysis**

**Outcome**: Understand current system scientifically
**Time**: 2-4 hours (when files readable)

### Phase 2: Small Fixes (Based on Data)
1. **Fix weight normalization** (if needed)
2. **Adjust weights** based on signal quality
3. **Fix specific failure modes** (if identified)
4. **Re-measure** with CI

**Outcome**: Small, evidence-based improvements
**Time**: 1-2 hours

### Phase 3: New Signals (Only If Data Supports)
1. **Text embeddings**: Only if signals are correlated/low quality
2. **GNN**: Only if graph structure helps
3. **Beam search**: Only if greedy fails specific cases

**Outcome**: Data-justified additions
**Time**: Variable

---

## Key Findings from Experiment Log

### What Didn't Work
1. **Frequency-based methods**: Consistently underperformed
2. **Metadata extraction**: Failed (files empty)
3. **Graph structure signals**: Didn't help (clustering, triangles)
4. **Weighted edges**: Slightly worse

### What Might Work
1. **Text embeddings**: Not tried yet (new signal)
2. **Better weight optimization**: Current weights may be suboptimal
3. **Signal quality improvement**: Fix low-quality signals

### Critical Insight
**Fusion is worse than baseline!** This suggests:
- Weights are wrong, OR
- Signals are correlated (redundant), OR
- One signal is hurting performance

**Action**: Measure individual signals to identify the issue

---

## Next Steps (Scientific)

1. **Run analysis scripts** (when files readable):
   ```bash
   # Measure individual signals
   python src/ml/analysis/measure_signal_performance.py
   
   # Analyze failures
   python src/ml/analysis/analyze_failures.py
   
   # Weight sensitivity
   python src/ml/analysis/weight_sensitivity.py --suggest
   ```

2. **Add CI to evaluation**:
   - Update evaluation code to use `evaluation_with_ci.py`
   - Re-run evaluation with CI
   - Report: "P@10 = 0.0882 ± 0.013 (95% CI)"

3. **Make data-driven fixes**:
   - Based on signal performance: adjust weights
   - Based on failures: fix specific issues
   - Based on sensitivity: small weight tweaks

4. **Re-measure**:
   - Compare before/after with CI
   - Ensure improvements are statistically significant

---

## Principle: No Changes Without Data

**Current State**: 
- Fusion (0.0882) < Baseline (0.089)
- Many experiments failed
- Test set is small (38 queries)

**Action**: 
- Measure first
- Understand why
- Fix specific issues
- Re-measure

**No speculative improvements** - only data-justified changes.







