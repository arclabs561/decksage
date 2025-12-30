# Critique: Labeling, Evaluation, and Training Pipeline

**Date**: 2025-12-27  
**Status**: Comprehensive analysis with actionable recommendations

---

## Executive Summary

The current pipeline has **three critical misalignments**:

1. **Training validation** doesn't measure what we care about (similarity quality)
2. **Evaluation** lacks statistical rigor (no confidence intervals, inconsistent query coverage)
3. **Labeling** has quality issues (sparse labels, no IAA tracking, fallback contamination)

**Impact**: We're optimizing for the wrong thing during training, evaluating with insufficient rigor, and using labels of uncertain quality.

---

## 1. Labeling Critique

### Current State

**Process**:
- LLM-as-judge generates labels (0-4 relevance scale)
- Fallback uses co-occurrence + embedding similarity when LLM fails
- 100 queries total, ~38 with LLM labels, rest with fallback

**Issues Identified**:

#### 1.1 Label Sparsity
- **Problem**: Many queries have <3 labels
- **Impact**: Cannot reliably compute P@10 (need at least 10 relevant items)
- **Evidence**: Test set analysis shows queries with 0-2 labels
- **Severity**: 🔴 **CRITICAL**

#### 1.2 No Inter-Annotator Agreement (IAA)
- **Problem**: No validation that labels are consistent or reliable
- **Impact**: Unknown label quality, cannot detect systematic errors
- **Evidence**: `inter_annotator_agreement.py` exists but not used in pipeline
- **Severity**: 🟡 **HIGH**

#### 1.3 Fallback Contamination
- **Problem**: Fallback uses embeddings to label, then we evaluate those same embeddings
- **Impact**: Circular evaluation - embeddings evaluated on labels they generated
- **Evidence**: `fallback_labeling.py` uses embedding similarity
- **Severity**: 🔴 **CRITICAL**

#### 1.4 No Label Quality Metrics
- **Problem**: No tracking of label confidence, disagreement, or uncertainty
- **Impact**: Cannot identify problematic queries or improve labeling
- **Severity**: 🟡 **MEDIUM**

#### 1.5 Single Judge
- **Problem**: Only one LLM judge per query
- **Impact**: No way to detect judge errors or inconsistencies
- **Severity**: 🟡 **MEDIUM**

### Recommendations

**Priority 1: Fix Circular Evaluation**
```python
# Current (BAD):
fallback_labeling.py uses embedding similarity → labels → evaluate embeddings

# Fix:
1. Use only co-occurrence for fallback (no embeddings)
2. Or: Use embeddings from different method for fallback
3. Or: Mark fallback labels and exclude from evaluation
```

**Priority 2: Expand Label Coverage**
- Target: **Minimum 10 labels per query** (for P@10)
- Strategy: Multi-judge LLM system (3 judges, majority vote)
- Fallback: Human annotation for queries with <10 labels

**Priority 3: Implement IAA**
- Run 3 LLM judges on same queries
- Compute Cohen's Kappa / Krippendorff's Alpha
- Flag queries with low agreement (<0.6) for review

**Priority 4: Label Quality Dashboard**
- Track: confidence scores, judge agreement, label distribution
- Identify: queries needing more labels, systematic errors
- Action: Re-label low-quality queries

---

## 2. Evaluation Critique

### Current State

**Metrics**: P@10, MRR  
**Test Set**: 38 queries (inconsistent coverage across methods)  
**Methods**: 6 embedding methods + Jaccard baseline

**Issues Identified**:

#### 2.1 No Confidence Intervals
- **Problem**: P@10 = 0.1429 reported without uncertainty
- **Impact**: Cannot tell if 0.1429 vs 0.1143 is statistically significant
- **Evidence**: `evaluation_results.json` has no `p@10_ci` or `mrr_ci`
- **Severity**: 🔴 **CRITICAL**

#### 2.2 Inconsistent Query Coverage
- **Problem**: Different methods evaluated on different numbers of queries (35-36)
- **Impact**: Comparisons are not fair (some methods get easier queries)
- **Evidence**: `node2vec_default`: 35 queries, `jaccard`: 36 queries
- **Severity**: 🟡 **HIGH**

#### 2.3 No Per-Query Breakdown
- **Problem**: Cannot identify which queries are hard/easy
- **Impact**: Cannot improve test set or understand failure modes
- **Severity**: 🟡 **MEDIUM**

#### 2.4 Limited Metrics
- **Problem**: Only P@10 and MRR
- **Impact**: Missing important aspects (recall, nDCG, task-specific metrics)
- **Severity**: 🟢 **LOW** (but should add nDCG)

#### 2.5 Small Test Set
- **Problem**: 38 queries is small for reliable evaluation
- **Impact**: High variance, unreliable comparisons
- **Evidence**: Need ~100+ queries for stable P@10 estimates
- **Severity**: 🟡 **MEDIUM**

#### 2.6 No Downstream Task Evaluation
- **Problem**: Only evaluates similarity, not deck completion/substitution
- **Impact**: Don't know if improvements translate to real tasks
- **Severity**: 🟡 **MEDIUM**

### Recommendations

**Priority 1: Add Confidence Intervals**
```python
# Bootstrap confidence intervals
def compute_ci(metrics, n_bootstrap=1000, confidence=0.95):
    """Compute bootstrap confidence intervals."""
    bootstrapped = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(metrics, size=len(metrics), replace=True)
        bootstrapped.append(np.mean(sample))
    return np.percentile(bootstrapped, [(1-confidence)/2*100, (1+confidence)/2*100])
```

**Priority 2: Standardize Query Coverage**
- Ensure all methods evaluated on **exact same queries**
- Filter queries where method fails (missing embeddings) separately
- Report coverage statistics

**Priority 3: Per-Query Analysis**
- Track P@10 per query
- Identify hard queries (all methods fail) vs easy queries
- Use for test set curation

**Priority 4: Expand Test Set**
- Target: **100+ queries** (current: 38)
- Strategy: Use multi-judge LLM to generate more high-quality labels
- Prioritize: Queries with diverse card types (creatures, spells, lands)

**Priority 5: Add nDCG**
- Better metric for ranking quality
- Accounts for position of relevant items
- Standard in information retrieval

**Priority 6: Downstream Task Evaluation**
- Deck completion: Can model complete decks?
- Card substitution: Can model suggest replacements?
- Measure: Completion rate, substitution quality

---

## 3. Training Critique

### Current State

**Validation**: Node overlap (checks if validation nodes in vocab)  
**Early Stopping**: Based on overlap score  
**Split**: 80% train, 10% val, 10% test

**Issues Identified**:

#### 3.1 Wrong Validation Metric
- **Problem**: Validates on node overlap, not similarity quality
- **Impact**: Optimizing for wrong objective (vocab coverage ≠ similarity)
- **Evidence**: `val_score = overlap / len(val_nodes)` - just checks if nodes exist
- **Severity**: 🔴 **CRITICAL**

#### 3.2 No Task Alignment
- **Problem**: Training doesn't use similarity labels or test set
- **Impact**: Model may overfit to graph structure, not similarity task
- **Severity**: 🔴 **CRITICAL**

#### 3.3 Validation Too Simple
- **Problem**: Overlap score will be ~1.0 for all epochs (all nodes in vocab)
- **Impact**: Early stopping doesn't work (no signal)
- **Evidence**: Validation score 0.9964 suggests saturation
- **Severity**: 🔴 **CRITICAL**

#### 3.4 No Overfitting Detection
- **Problem**: No comparison of train vs val performance
- **Impact**: Cannot detect if model memorizes training data
- **Severity**: 🟡 **MEDIUM**

#### 3.5 No Hyperparameter Validation
- **Problem**: Hyperparameter search uses test set (data leakage)
- **Impact**: Overfitting to test set, optimistic results
- **Severity**: 🟡 **HIGH**

### Recommendations

**Priority 1: Fix Validation Metric**
```python
# Current (BAD):
val_score = overlap / len(val_nodes)  # Just checks if nodes exist

# Fix:
# Option A: Validate on similarity task
val_queries = sample_from_test_set(n=20)
val_score = evaluate_similarity(model, val_queries, test_set)

# Option B: Validate on graph reconstruction
val_score = evaluate_link_prediction(model, val_edges)

# Option C: Validate on downstream task
val_score = evaluate_deck_completion(model, val_decks)
```

**Priority 2: Use Test Set for Validation**
- Split test set: 70% for validation during training, 30% for final evaluation
- Or: Use cross-validation on test set
- **Never use test set for hyperparameter tuning**

**Priority 3: Add Overfitting Detection**
- Track train vs val similarity scores
- Stop if val plateaus while train improves
- Report train/val gap

**Priority 4: Task-Specific Training**
- Consider supervised fine-tuning on similarity labels
- Or: Multi-task learning (unsupervised + similarity)
- Or: Contrastive learning with positive/negative pairs

**Priority 5: Hyperparameter Search Fix**
- Use validation set for hyperparameter search
- Keep test set completely separate
- Report: "Best hyperparams on val, final eval on test"

---

## 4. Cross-Cutting Issues

### 4.1 Data Leakage
- **Problem**: Test set used for multiple purposes (labeling, evaluation, potentially hyperparameter search)
- **Impact**: Overfitting, optimistic results
- **Fix**: Strict train/val/test split, never reuse test set

### 4.2 No Experiment Tracking
- **Problem**: No systematic tracking of experiments, hyperparameters, results
- **Impact**: Cannot reproduce results or learn from history
- **Fix**: Use Aim or MLflow for experiment tracking

### 4.3 No A/B Testing Framework
- **Problem**: Cannot rigorously compare methods
- **Impact**: Unclear if improvements are real or noise
- **Fix**: Implement statistical significance testing

### 4.4 Evaluation Not Integrated with Training
- **Problem**: Training and evaluation are separate
- **Impact**: Training doesn't benefit from evaluation insights
- **Fix**: Use evaluation metrics for validation during training

---

## 5. Recommended Action Plan

### Phase 1: Fix Critical Issues (1-2 weeks)

1. **Fix circular evaluation** (1 day)
   - Remove embedding similarity from fallback labeling
   - Use only co-occurrence for fallback
   - Re-label queries that used embedding fallback

2. **Fix validation metric** (2 days)
   - Implement similarity-based validation
   - Use test set split for validation
   - Update training script

3. **Add confidence intervals** (1 day)
   - Implement bootstrap CIs for P@10, MRR
   - Update evaluation script
   - Re-run evaluation

### Phase 2: Improve Quality (2-3 weeks)

4. **Expand test set** (1 week)
   - Generate 100+ queries with multi-judge LLM
   - Ensure minimum 10 labels per query
   - Implement IAA tracking

5. **Implement IAA** (3 days)
   - Run 3 LLM judges on same queries
   - Compute agreement metrics
   - Flag low-agreement queries

6. **Per-query analysis** (2 days)
   - Track P@10 per query
   - Identify hard/easy queries
   - Create test set quality dashboard

### Phase 3: Advanced Improvements (3-4 weeks)

7. **Downstream task evaluation** (1 week)
   - Implement deck completion evaluation
   - Implement card substitution evaluation
   - Integrate with training validation

8. **Experiment tracking** (3 days)
   - Set up Aim or MLflow
   - Track all experiments systematically
   - Create experiment comparison dashboard

9. **A/B testing framework** (1 week)
   - Implement statistical significance testing
   - Create framework for method comparison
   - Document best practices

---

## 6. Quick Wins (Can Do Now)

1. **Add confidence intervals to evaluation** (2 hours)
   - Bootstrap CIs are easy to implement
   - Immediate improvement in evaluation rigor

2. **Fix validation metric** (4 hours)
   - Switch from node overlap to similarity validation
   - Immediate improvement in training quality

3. **Remove embedding fallback** (1 hour)
   - Quick fix for circular evaluation
   - Use only co-occurrence

4. **Standardize query coverage** (1 hour)
   - Ensure all methods use same queries
   - Fair comparison

---

## 7. Metrics to Track

### Labeling Quality
- Labels per query (target: ≥10)
- IAA (Cohen's Kappa, target: ≥0.6)
- Label distribution (should be diverse, not all 0s or 4s)
- Judge agreement rate

### Evaluation Quality
- Confidence intervals (95% CI for all metrics)
- Query coverage (should be 100% for all methods)
- Per-query P@10 (identify hard queries)
- Statistical significance (p-values for comparisons)

### Training Quality
- Train/val similarity gap (detect overfitting)
- Validation score trend (should improve then plateau)
- Early stopping effectiveness
- Hyperparameter sensitivity

---

## 8. Success Criteria

**Labeling**:
- ✅ 100+ queries with ≥10 labels each
- ✅ IAA ≥ 0.6 for all queries
- ✅ No circular evaluation (no embedding fallback)

**Evaluation**:
- ✅ Confidence intervals for all metrics
- ✅ 100% query coverage for all methods
- ✅ Per-query analysis available
- ✅ Statistical significance testing

**Training**:
- ✅ Validation uses similarity task (not node overlap)
- ✅ Train/val gap tracked
- ✅ Early stopping works (val score plateaus)
- ✅ No test set leakage

---

## Conclusion

The pipeline has **fundamental misalignments** that prevent reliable improvement:

1. **Training optimizes for wrong thing** (node overlap ≠ similarity)
2. **Evaluation lacks rigor** (no CIs, inconsistent coverage)
3. **Labeling has quality issues** (sparse, circular, no IAA)

**Fix these first** before attempting further improvements. The current approach will plateau because we're not measuring what we care about.

**Next Steps**: Start with Phase 1 (fix critical issues) - these are quick wins that will have immediate impact.
