# Data-Driven Analysis and Improvements

**Date**: November 10, 2025
**Approach**: Scientific, data-motivated, error-review driven
**Principle**: Small, quintessential changes based on evidence

---

## Current Performance Baseline

### Measured Performance
- **P@10**: 0.0882 (8.82% precision at top 10)
- **Game**: Magic: The Gathering
- **Test Set**: Canonical test sets exist (magic, pokemon, yugioh)
- **Best Weights**: `embed=0.1, jaccard=0.2, functional=0.7`

### Statistical Context
- **Sample Size**: Need to verify (test sets exist but size unknown)
- **Confidence Intervals**: Not reported (critical gap)
- **Cross-Game Performance**: Test sets exist but comparison needed

---

## Data Analysis Plan

### Step 1: Analyze Test Set Composition
**Hypothesis**: Test set may be biased or too small
**Data Needed**:
- Number of queries per game
- Query distribution (archetypes, card types)
- Label quality (human vs LLM)

**Action**: Analyze test set files to understand composition

### Step 2: Error Analysis
**Hypothesis**: Specific failure modes exist
**Data Needed**:
- Which queries fail (P@10 = 0)?
- Which card types are hardest?
- Which similarity modes fail?

**Action**: Analyze experiment logs and failed tests

### Step 3: Weight Sensitivity Analysis
**Hypothesis**: Current weights may be suboptimal
**Data Needed**:
- Grid search explored space
- Weight sensitivity (how much does P@10 change with weight changes?)
- Interaction effects between weights

**Action**: Analyze fusion_grid_search results

### Step 4: Signal Quality Analysis
**Hypothesis**: Individual signals may have different quality
**Data Needed**:
- P@10 for each signal alone (embed, jaccard, functional)
- Correlation between signals
- Signal coverage (how many queries have each signal?)

**Action**: Measure individual signal performance

---

## Evidence-Based Improvement Strategy

### Principle: Measure First, Improve Second

1. **Baseline Measurement**
   - Measure P@10 for each signal individually
   - Measure correlation between signals
   - Identify queries where all signals fail

2. **Error Pattern Analysis**
   - Categorize failures by card type, archetype, format
   - Identify systematic biases
   - Find edge cases

3. **Targeted Improvements**
   - Fix specific failure modes (not general improvements)
   - Optimize weights based on signal quality
   - Add signals only where gaps exist

---

## Specific Analysis Tasks

### Task 1: Measure Individual Signal Performance
```python
# Analysis script needed
# For each signal (embed, jaccard, functional):
#   - Compute P@10 using only that signal
#   - Measure on test set
#   - Compare to baseline (0.0882)
```

**Expected Findings**:
- If one signal is much better: Increase its weight
- If signals are correlated: Reduce redundancy
- If all signals are similar: Need new signal (text embeddings)

### Task 2: Analyze Failure Cases
```python
# Analysis script needed
# For each query in test set:
#   - Compute predictions
#   - Check if any relevant cards in top 10
#   - Categorize failure type
```

**Failure Categories**:
- **No relevant cards**: Signal quality issue
- **Relevant cards ranked low**: Weight/aggregation issue
- **Wrong card type**: Type filtering needed
- **Format mismatch**: Format awareness needed

### Task 3: Weight Sensitivity Analysis
```python
# Re-analyze grid search results
# For each weight combination:
#   - Measure P@10
#   - Identify optimal region
#   - Check if current weights are in optimal region
```

**Questions**:
- Is functional=0.7 actually optimal?
- Could small weight adjustments improve P@10?
- Are there local optima we're missing?

---

## Small, Quintessential Improvements

Based on data analysis, make minimal changes:

### Improvement 1: Add Confidence Intervals
**Why**: Current P@10=0.0882 has no uncertainty measure
**Change**: Add bootstrapped 95% CI to evaluation
**Impact**: Know if improvements are statistically significant
**Effort**: Small (add CI computation to evaluation)

### Improvement 2: Fix Weight Normalization
**Why**: Weights may not be properly normalized
**Change**: Ensure weights sum to 1.0 in fusion
**Impact**: Small but correct
**Effort**: Minimal (one-line fix)

### Improvement 3: Measure Signal Coverage
**Why**: Some queries may lack certain signals
**Change**: Track which signals available per query
**Impact**: Understand failure modes
**Effort**: Small (add logging)

### Improvement 4: Analyze Weight Sensitivity
**Why**: Current weights may be suboptimal
**Change**: Re-run grid search with finer granularity around current best
**Impact**: Potentially +0.01-0.02 P@10
**Effort**: Medium (re-run grid search)

---

## Implementation Priority

### Phase 1: Measurement (Do First)
1. Measure individual signal P@10
2. Add confidence intervals
3. Analyze failure cases
4. Measure signal coverage

**Outcome**: Understand current system scientifically

### Phase 2: Targeted Fixes (Based on Data)
1. Fix weight normalization if needed
2. Adjust weights based on signal quality
3. Fix specific failure modes
4. Add missing signal coverage

**Outcome**: Small, evidence-based improvements

### Phase 3: New Signals (If Data Supports)
1. Add text embeddings only if signals are correlated
2. Add GNN only if graph structure helps
3. Add beam search only if greedy fails specific cases

**Outcome**: Data-justified additions

---

## Analysis Scripts Needed

### Script 1: Individual Signal Performance
```python
# src/ml/analysis/measure_signal_performance.py
# - Load test set
# - For each signal: compute P@10
# - Report: signal_name, P@10, std_err, n_queries
```

### Script 2: Failure Case Analysis
```python
# src/ml/analysis/analyze_failures.py
# - Load test set and predictions
# - Categorize failures
# - Report: failure_type, count, examples
```

### Script 3: Weight Sensitivity
```python
# src/ml/analysis/weight_sensitivity.py
# - Load grid search results
# - Plot P@10 vs weights
# - Identify optimal region
```

---

## Next Steps

1. **Create analysis scripts** (measure first)
2. **Run analysis** (understand current state)
3. **Identify specific issues** (data-driven)
4. **Make minimal fixes** (targeted improvements)
5. **Re-measure** (validate improvements)

**Principle**: No changes without data justification.
