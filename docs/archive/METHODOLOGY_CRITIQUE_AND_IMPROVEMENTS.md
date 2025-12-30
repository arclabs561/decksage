# Methodology Critique and Improvements

**Date**: November 10, 2025  
**Based on**: Scientific best practices, bootstrap methods, fusion evaluation

---

## Current Methodology Issues

### Issue 1: No Confidence Intervals
**Problem**: P@10 = 0.0882 reported without uncertainty
**Impact**: Can't tell if 0.088 vs 0.089 is meaningful
**Fix**: ✅ Already implemented `evaluation_with_ci.py`

### Issue 2: Small Sample Size
**Problem**: 38 queries is small for statistical power
**Bootstrap Guidance**: 
- For n=38, 95% CI width ≈ ±0.05 for P@10=0.09
- Need n=100+ for ±0.02 CI width
**Fix**: Report CI, consider expanding test set

### Issue 3: No Individual Signal Measurement
**Problem**: Don't know which signals help/hurt
**Impact**: Can't optimize weights scientifically
**Fix**: ✅ Script created, need to run

### Issue 4: Fusion Worse Than Baseline
**Problem**: Fusion (0.0882) < Jaccard alone (0.089)
**Hypothesis**: 
- Weights wrong
- Signals correlated (redundant)
- One signal hurting
**Fix**: Measure individual signals first

### Issue 5: No Failure Analysis
**Problem**: 71% of experiments made things worse, but don't know why
**Impact**: Repeating failed approaches
**Fix**: ✅ Script created, need to run

---

## Methodology Improvements

### Improvement 1: Bootstrap Confidence Intervals ✅
**Implementation**: `src/ml/utils/evaluation_with_ci.py`
**Usage**:
```python
from ml.utils.evaluation_with_ci import evaluate_with_confidence

results = evaluate_with_confidence(
    test_set,
    similarity_func,
    top_k=10,
    n_bootstrap=1000,
    confidence=0.95,
)

# Report: "P@10 = 0.0882 (95% CI: 0.075, 0.101)"
```

**Best Practice**: Always report CI for small samples

### Improvement 2: Individual Signal Measurement
**Implementation**: `src/ml/analysis/measure_signal_performance.py`
**Purpose**: Measure P@10 for each signal independently

**Methodology**:
1. For each signal (embed, jaccard, functional):
   - Compute similarity using only that signal
   - Measure P@10 on test set
   - Report: mean, CI, std_err

2. Compare to fusion:
   - If one signal much better: Increase its weight
   - If signals correlated: Remove redundancy
   - If all signals weak: Need new signals

**Best Practice**: Understand signal quality before fusion

### Improvement 3: Failure Case Categorization
**Implementation**: `src/ml/analysis/analyze_failures.py`
**Purpose**: Understand why predictions fail

**Categories**:
- `no_relevant_in_top_k`: No relevant cards found
- `partial_relevant`: Some relevant, not all
- `ranking_issue`: Relevant cards ranked low
- `no_labels`: Test set issue

**Best Practice**: Categorize failures to identify fixable issues

### Improvement 4: Weight Sensitivity Analysis
**Implementation**: `src/ml/analysis/weight_sensitivity.py`
**Purpose**: Understand weight space

**Methodology**:
1. Analyze grid search results
2. Compute correlation: weight vs P@10
3. Identify optimal region
4. Suggest small adjustments

**Best Practice**: Understand weight space before optimization

### Improvement 5: Format-Aware Evaluation
**Finding**: Best result (0.150) used format-specific embeddings
**Implementation**: `src/ml/similarity/format_aware_similarity.py`
**Purpose**: Replicate successful approach

**Methodology**:
1. Verify if current embeddings are format-aware
2. If not, implement format-specific embeddings
3. Measure improvement

**Best Practice**: Replicate successful experiments

---

## Scientific Evaluation Workflow

### Step 1: Baseline Measurement
```python
# Measure with CI
results = evaluate_with_confidence(test_set, baseline_similarity)
# Report: "Baseline P@10 = 0.089 (95% CI: 0.075, 0.103)"
```

### Step 2: Individual Signal Measurement
```python
# Measure each signal
embed_results = measure_signal_performance(test_set, embed_similarity)
jaccard_results = measure_signal_performance(test_set, jaccard_similarity)
functional_results = measure_signal_performance(test_set, functional_similarity)

# Compare
print(f"Embed: {embed_results['mean_p_at_k']:.4f} ± {embed_results['std_err']:.4f}")
print(f"Jaccard: {jaccard_results['mean_p_at_k']:.4f} ± {jaccard_results['std_err']:.4f}")
print(f"Functional: {functional_results['mean_p_at_k']:.4f} ± {functional_results['std_err']:.4f}")
```

### Step 3: Failure Analysis
```python
# Analyze failures
failures = analyze_failures(test_set, predictions)
# Categorize and identify patterns
```

### Step 4: Targeted Improvement
```python
# Based on data:
# - If one signal better: Adjust weights
# - If signals correlated: Remove redundancy
# - If format helps: Add format awareness
```

### Step 5: Re-measurement
```python
# Re-measure with CI
new_results = evaluate_with_confidence(test_set, improved_similarity)
# Compare: Is improvement statistically significant?
```

---

## Bootstrap Methodology (Best Practices)

### For Small Samples (n=38)
- **Bootstrap samples**: 1000+ (we use 1000)
- **CI method**: Percentile method (2.5th, 97.5th percentiles)
- **Interpretation**: 
  - If CI overlap: Not statistically different
  - If CI don't overlap: Statistically different

### Reporting Format
```
P@10 = 0.0882 (95% CI: 0.0751, 0.1013, n=38)
```

### Statistical Power
- **Current**: n=38, CI width ≈ ±0.013
- **Ideal**: n=100+, CI width ≈ ±0.02
- **Action**: Consider expanding test set for better power

---

## Fusion Weight Optimization Methodology

### Current Approach (Grid Search)
- **Grid**: Step size 0.1
- **Space**: embed × jaccard × functional
- **Result**: embed=0.1, jaccard=0.2, functional=0.7

### Improved Approach
1. **Measure individual signals first**
2. **Identify optimal region** (weight sensitivity)
3. **Fine-tune around optimal** (smaller step size)
4. **Validate with CI** (ensure improvement is significant)

### Signal Correlation Analysis
**Method**: Measure correlation between signals
- If high correlation (>0.7): Signals redundant
- If low correlation (<0.3): Signals complementary
- **Action**: Remove redundant signals, keep complementary

---

## Critical Methodology Fixes

### Fix 1: Always Report CI
**Current**: "P@10 = 0.0882"
**Improved**: "P@10 = 0.0882 (95% CI: 0.075, 0.101, n=38)"
**Impact**: Statistical rigor

### Fix 2: Measure Before Optimizing
**Current**: Optimize weights without knowing signal quality
**Improved**: Measure individual signals, then optimize
**Impact**: Data-driven optimization

### Fix 3: Understand Failures
**Current**: 71% experiments failed, don't know why
**Improved**: Categorize failures, identify patterns
**Impact**: Avoid repeating mistakes

### Fix 4: Replicate Success
**Current**: Best result (0.150) not replicated
**Improved**: Implement format-aware similarity
**Impact**: Potential +70% improvement

---

## Implementation Checklist

### Immediate (Methodology Fixes)
- [x] Add CI to evaluation ✅
- [ ] Run individual signal measurement
- [ ] Run failure analysis
- [ ] Run weight sensitivity analysis
- [ ] Implement format-aware similarity

### Next (Based on Data)
- [ ] Adjust weights based on signal quality
- [ ] Remove redundant signals (if found)
- [ ] Fix specific failure modes
- [ ] Re-measure with CI

### Future (If Justified)
- [ ] Expand test set to 100+ queries
- [ ] Add text embeddings (if signals weak)
- [ ] Add GNN (if graph structure helps)

---

## Files Created (Ready to Use)

1. ✅ `src/ml/utils/evaluation_with_ci.py` - CI computation
2. ✅ `src/ml/analysis/measure_signal_performance.py` - Signal measurement
3. ✅ `src/ml/analysis/analyze_failures.py` - Failure analysis
4. ✅ `src/ml/analysis/weight_sensitivity.py` - Weight analysis
5. ✅ `src/ml/analysis/find_best_experiment.py` - Find successful methods
6. ✅ `src/ml/similarity/format_aware_similarity.py` - Format awareness

**Status**: All tools ready, need to run when files readable.

---

## Next Steps

1. **When files readable**: Run analysis scripts
2. **Based on results**: Make targeted fixes
3. **Re-measure**: With CI to validate
4. **Document**: Methodology and findings

**Principle**: Measure → Understand → Fix → Validate







