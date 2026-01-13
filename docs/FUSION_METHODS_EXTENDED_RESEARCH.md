# Extended Fusion Methods Research: Learning from rank-fusion Repository

**Date:** January 6, 2026
**Source:** https://github.com/arclabs561/rank-fusion
**Status:** Research Complete - Recommendations Provided

## Executive Summary

After reviewing the `rank-fusion` repository, we've identified several additional fusion methods that could improve our system. **ISR (Inverse Square Root)** and **CombMNZ** are the most promising additions. **Borda count** and **DBSF** are worth considering for specific use cases.

## Methods Comparison

### Current Implementation ✅

| Method | Status | Use Case |
|--------|--------|----------|
| **RRF** | ✅ Implemented | Incompatible score scales (default) |
| **Weighted** | ✅ Implemented | Custom retriever weights |
| **CombSUM** | ✅ Implemented | Similar scales, trust scores |
| **CombMAX** | ✅ Implemented | Optimistic aggregation |
| **CombMIN** | ✅ Implemented | Pessimistic aggregation |

### Additional Methods from rank-fusion

| Method | Status | Best For | Complexity |
|--------|--------|----------|------------|
| **ISR** | ❌ Not implemented | When lower ranks matter more | Low |
| **CombMNZ** | ❌ Not implemented | Reward overlap between lists | Low |
| **Borda** | ❌ Not implemented | Simple voting | Low |
| **DBSF** | ❌ Not implemented | Different score distributions | Medium |
| **Condorcet** | ❌ Not implemented | Pairwise comparisons | High |

## Detailed Method Analysis

### 1. ISR (Inverse Square Root) - **RECOMMENDED**

**Formula:**
```
ISR_Score(d) = Σ (1 / sqrt(k + rank_i(d)))
```

**Comparison to RRF:**
- RRF: `1 / (k + rank)` - reciprocal (faster decay)
- ISR: `1 / sqrt(k + rank)` - square root (slower decay)

**When to Use:**
- ✅ When lower ranks matter more (less aggressive decay)
- ✅ When you want to give more weight to items ranked 10-50
- ✅ Alternative to RRF for different rank sensitivity

**Implementation Complexity:** Low (similar to RRF)

**Recommendation:** ✅ **Implement** - Easy addition, useful alternative to RRF

### 2. CombMNZ (Combined Multiple Normalized Z-scores) - **RECOMMENDED**

**Formula:**
```
CombMNZ_Score(d) = (Σ normalized_score_i(d)) × count(d)
```

Where `count(d)` is the number of lists containing document `d`.

**Key Difference from CombSUM:**
- CombSUM: Just sums normalized scores
- CombMNZ: Sums scores **multiplied by overlap count** (rewards agreement)

**When to Use:**
- ✅ When you want to reward documents appearing in multiple lists
- ✅ When agreement between retrievers is important
- ✅ Better than CombSUM when you have multiple heterogeneous retrievers

**Implementation Complexity:** Low (similar to CombSUM)

**Recommendation:** ✅ **Implement** - Simple, rewards agreement (important for our multi-modal setup)

### 3. Borda Count - **CONSIDER**

**Formula:**
```
Borda_Score(d) = Σ (n - rank_i(d))
```

Where `n` is the total number of documents in list `i`.

**When to Use:**
- ✅ Simple voting-based approach
- ✅ Linear rank weighting (unlike RRF's reciprocal)
- ⚠️ Less sophisticated than RRF/ISR

**Implementation Complexity:** Low

**Recommendation:** ⚠️ **Consider** - Simple but less powerful than RRF/ISR

### 4. DBSF (Distribution-Based Score Fusion) - **CONSIDER**

**Description:** Handles different score distributions by normalizing based on distribution characteristics.

**When to Use:**
- ✅ When score distributions vary significantly
- ✅ When you have heterogeneous retrievers with different score scales
- ⚠️ More complex than other methods

**Implementation Complexity:** Medium (requires distribution analysis)

**Recommendation:** ⚠️ **Consider** - Useful but we already handle this with normalization

### 5. Condorcet Voting - **NOT RECOMMENDED**

**Description:** Pairwise comparisons to find documents that beat all others head-to-head.

**Limitations:**
- ❌ Condorcet winner doesn't always exist
- ❌ High computational complexity (O(n²) comparisons)
- ❌ Less suitable for ranking (designed for voting)

**Recommendation:** ❌ **Skip** - Too complex, not designed for ranking

## Implementation Recommendations

### Phase 1: High-Value Additions (Immediate)

1. **ISR (Inverse Square Root)**
   - Easy to implement (similar to RRF)
   - Provides alternative rank sensitivity
   - Useful for queries where lower ranks matter

2. **CombMNZ (Combined Multiple Normalized Z-scores)**
   - Simple addition to existing CombSUM
   - Rewards agreement between modalities
   - Particularly useful for our multi-modal setup

### Phase 2: Optional Additions (Future)

3. **Borda Count**
   - Simple voting method
   - Less powerful than RRF/ISR but simpler
   - Could be useful for baseline comparisons

4. **DBSF (Distribution-Based Score Fusion)**
   - More sophisticated normalization
   - May not be needed if our current normalization works well

### Phase 3: Skip

5. **Condorcet Voting**
   - Too complex for ranking tasks
   - Not designed for information retrieval

## Implementation Plan

### Step 1: Add ISR Method

```python
def _aggregate_isr(self, ranks: dict[str, int]) -> float:
    """Inverse Square Root rank fusion."""
    import math
    total = 0.0
    if self.weights.embed > 0.0 and "embed" in ranks:
        total += self.weights.embed / math.sqrt(self.rrf_k + ranks["embed"])
    # ... (same pattern for all modalities)
    return total
```

### Step 2: Add CombMNZ Method

```python
def _aggregate_combmnz(self, scores: dict[str, float], overlap_count: int) -> float:
    """Combined Multiple Normalized Z-scores (rewards agreement)."""
    # Sum of normalized scores
    score_sum = self._aggregate_combsum(scores)
    # Multiply by overlap count (number of lists containing this document)
    return score_sum * overlap_count
```

### Step 3: Update Aggregator Selection

```python
aggregator: str = "rrf",  # Options: "rrf", "isr", "weighted", "combsum", "combmnz", "combmax", "combmin"
```

## Performance Considerations

Based on rank-fusion repository documentation:

- **RRF**: ~3-4% lower NDCG than score-based fusion, but ~1-2% faster
- **ISR**: Similar performance to RRF, different rank sensitivity
- **CombMNZ**: Better than CombSUM when agreement matters
- **Borda**: Simpler but less powerful than RRF/ISR

## Testing Strategy

1. **Compare ISR vs RRF** on our test set
2. **Compare CombMNZ vs CombSUM** on multi-modal queries
3. **Ablation study** to determine when each method works best
4. **Performance benchmarks** for all methods

## Conclusion

**Immediate Actions:**
1. ✅ Implement ISR (easy, useful alternative to RRF)
2. ✅ Implement CombMNZ (rewards agreement, important for multi-modal)

**Future Considerations:**
3. ⚠️ Consider Borda for baseline comparisons
4. ⚠️ Consider DBSF if normalization issues arise

**Skip:**
5. ❌ Condorcet (too complex, not designed for ranking)

The addition of ISR and CombMNZ will give us more flexibility and better handling of multi-modal agreement, which is crucial for our heterogeneous similarity signals.
