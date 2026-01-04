# Targeted Improvement Based on Data Analysis

**Date**: November 10, 2025
**Finding**: Best experiment achieved P@10=0.150 (70% better than current)
**Method**: "Separate Node2Vec per format" (exp_025)

---

## Critical Discovery

### Best Performing Experiment
- **Experiment ID**: exp_025
- **Method**: "Separate Node2Vec per format"
- **P@10**: 0.150 (vs current 0.0882)
- **Improvement**: +70% over current fusion

### Key Insight
**Format-specific embeddings work better than format-agnostic!**

**Implication**:
- Current system may be mixing formats incorrectly
- Need format-aware similarity
- This is a small, targeted fix (not a major rewrite)

---

## Data-Driven Improvement

### Improvement: Format-Aware Similarity
**Why**: Best result (0.150) used format-specific embeddings
**Current Issue**: Fusion may be using format-agnostic embeddings

**Small Change**:
1. Check if similarity functions are format-aware
2. If not, add format filtering to embeddings
3. Use format-specific embedding models if available

**Expected Impact**:
- If current embeddings are format-agnostic: +0.03-0.06 P@10 (0.088 → 0.12-0.15)
- If already format-aware: No change (need other fix)

**Effort**: Small (format filtering is simple)

---

## Other Top Performers (For Reference)

1. **exp_025**: Separate Node2Vec per format - **0.150** ⭐ BEST
2. **exp_031**: Jaccard weighted by PageRank - 0.119
3. **exp_035**: Jaccard weighted by co-occurrence - 0.119
4. **exp_037**: Jaccard + Clustering coefficient - 0.118
5. **exp_033**: Jaccard + Frequency (70/30) - 0.101

**Pattern**: All top performers use Jaccard as base, add graph/format awareness

---

## Scientific Implementation Plan

### Step 1: Verify Current Format Awareness
**Question**: Are current embeddings format-specific or format-agnostic?

**Check**:
- How are embeddings loaded? (single model vs per-format)
- How is format used in similarity computation?
- Are format filters applied?

**Action**: Review embedding loading code

### Step 2: Implement Format-Aware Similarity (If Needed)
**Change**:
- Load format-specific embedding models
- Filter embeddings by format in similarity
- Use format from deck/query context

**Implementation**:
```python
# In similarity computation:
def format_aware_similarity(query_card, candidate_card, format_name):
    # Load format-specific embeddings if available
    embeddings = load_format_embeddings(format_name)
    # Compute similarity using format-specific model
    return compute_similarity(query_card, candidate_card, embeddings)
```

### Step 3: Measure Impact
**Action**:
- Re-run evaluation with format-aware similarity
- Compare: format-aware vs format-agnostic
- Measure P@10 improvement

**Expected**: P@10 improvement from 0.088 → 0.12-0.15

---

## Additional Findings

### Why Current Fusion Fails
**Current**: embed=0.1, jaccard=0.2, functional=0.7 → P@10=0.0882
**Baseline**: Jaccard alone → P@10=0.089
**Finding**: Fusion is worse than baseline!

**Hypothesis**:
- Functional tags (0.7 weight) may be low quality
- Embeddings (0.1 weight) may be format-agnostic (hurting performance)
- Need to measure individual signals

### Pattern from Top Performers
All top 5 use **Jaccard as base**:
- Jaccard + format awareness
- Jaccard + graph metrics (PageRank, clustering)
- Jaccard + frequency

**Implication**: Jaccard is the strongest signal, other signals should enhance it

---

## Small, Quintessential Fixes

### Fix 1: Format-Aware Embeddings (HIGH PRIORITY)
**Based on**: exp_025 achieved 0.150 with format-specific embeddings
**Change**: Use format-specific embedding models
**Impact**: Potentially +0.03-0.06 P@10
**Effort**: Small (format filtering)

### Fix 2: Measure Individual Signals
**Based on**: Fusion worse than baseline - need to know why
**Change**: Measure P@10 for each signal alone
**Impact**: Understand signal quality
**Effort**: Medium (implement measurement)

### Fix 3: Adjust Weights Based on Signal Quality
**Based on**: If one signal is much better, increase its weight
**Change**: Optimize weights based on individual signal P@10
**Impact**: Potentially +0.01-0.02 P@10
**Effort**: Small (re-run grid search)

### Fix 4: Add Confidence Intervals
**Based on**: Test set is small (38 queries), need statistical rigor
**Change**: Use evaluation_with_ci.py
**Impact**: Know if changes are significant
**Effort**: Small (already implemented)

---

## Implementation Priority

### Immediate (Based on Data)
1. **Verify format awareness** in current embeddings
2. **Implement format-aware similarity** (if needed)
3. **Re-measure** with format awareness
4. **Compare** to exp_025 result (0.150)

### Next (Based on Analysis)
1. **Measure individual signals** (understand why fusion < baseline)
2. **Adjust weights** (based on signal quality)
3. **Add CI** (statistical rigor)

### Future (Only If Data Supports)
1. **Text embeddings**: Only if all signals are weak
2. **GNN**: Only if graph structure helps
3. **Beam search**: Only if greedy fails

---

## Expected Outcomes

### With Format-Aware Similarity
- **Current**: P@10 = 0.0882
- **Expected**: P@10 = 0.12-0.15 (based on exp_025)
- **Improvement**: +36-70%

### With Weight Optimization
- **Current**: P@10 = 0.0882
- **Expected**: P@10 = 0.09-0.10 (small improvement)
- **Improvement**: +2-13%

### Combined
- **Expected**: P@10 = 0.13-0.16
- **Improvement**: +47-81%

---

## Principle: Data-Driven, Small Changes

**No speculative improvements**:
1. ✅ Found best method (exp_025) - replicate it
2. ⏳ Measure individual signals - understand current state
3. ⏳ Fix format awareness - small, targeted change
4. ⏳ Optimize weights - based on signal quality

**All changes justified by data from experiment log.**
