# Individual Signal Performance Analysis

**Date**: 2025-01-27  
**Test Set**: `experiments/test_set_canonical_magic.json` (38 queries)

---

## Results

| Signal | P@10 | MRR | Queries Evaluated |
|--------|------|-----|-------------------|
| **Embedding** (Node2Vec-Default) | **0.1429** | **0.0812** | 35 |
| **Jaccard** | 0.0833 | 0.0472 | 36 |
| **Functional** | Not implemented | - | - |

---

## Key Findings

### 1. Embedding Signal is Strongest
- **P@10: 0.1429** - 72% better than Jaccard
- **MRR: 0.0812** - 72% better than Jaccard
- Node2Vec embeddings capture similarity better than co-occurrence alone

### 2. Jaccard Baseline
- **P@10: 0.0833** - Matches previous baseline measurement
- **MRR: 0.0472** - Lower than embedding
- Co-occurrence alone is weaker signal

### 3. Signal Comparison
- **Embedding > Jaccard**: 0.1429 vs 0.0833 (72% improvement)
- This explains why fusion with embeddings helps

---

## Implications for Fusion

### Current Fusion Performance
- **Fusion P@10: 0.0882** (from previous analysis)
- **Jaccard alone: 0.0833**
- **Embedding alone: 0.1429**

### Problem Identified
- Fusion (0.0882) is **worse** than embedding alone (0.1429)
- Fusion is only slightly better than Jaccard alone (0.0833)
- **Conclusion**: Fusion weights are suboptimal - embedding signal is being diluted

### Recommended Fix
1. **Increase embedding weight** - It's the strongest signal
2. **Decrease Jaccard weight** - It's weaker
3. **Measure functional signal** - Need to know its contribution
4. **Re-optimize weights** - Based on individual signal performance

---

## Next Steps

1. ✅ Measure embedding signal - **DONE** (0.1429)
2. ✅ Measure Jaccard signal - **DONE** (0.0833)
3. ⏳ Measure functional signal - **TODO**
4. ⏳ Re-optimize fusion weights based on signal strengths
5. ⏳ Measure fusion performance with new weights

---

## Files

- `experiments/individual_signal_performance.json` - Full results
- `src/ml/scripts/measure_individual_signals.py` - Measurement script (PEP 723)

---

**Status**: ✅ Individual signals measured, fusion weights need re-optimization

