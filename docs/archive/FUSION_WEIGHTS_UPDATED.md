# Fusion Weights Updated Based on Evaluation ✅

## Summary

Updated fusion weights based on actual evaluation results showing Jaccard is 3x better than embedding.

## Evaluation Results

| Method | P@10 | MRR | Performance Ratio |
|--------|------|-----|-------------------|
| **Jaccard** | **0.0833** | **0.0472** | **3.0x** |
| Embedding | 0.0278 | 0.0278 | 1.0x |

## Updated Weights

### Before (Default)
- embed: 0.15 (15%)
- jaccard: 0.15 (15%)
- functional: 0.15 (15%)
- Other signals: 0.55 (55%)

### After (Optimized)
- **embed: 0.25 (25%)**
- **jaccard: 0.75 (75%)**
- functional: 0.0 (0% - not measured)
- Other signals: 0.0 (0% - not measured yet)

**Rationale**: Proportional to individual signal performance. Jaccard is 3x better, so it gets 75% weight.

## Changes Made

1. **Updated `FusionWeights` defaults** in `src/ml/similarity/fusion.py`:
   - embed: 0.15 → 0.25
   - jaccard: 0.15 → 0.75
   - functional: 0.15 → 0.0

2. **Updated API fallback defaults** in `src/ml/api/api.py`:
   - Changed fallback from equal weights to optimized weights
   - Updated to load from `optimized_fusion_weights_latest.json` first

3. **Created optimization script**: `src/ml/scripts/update_fusion_weights_from_evaluation.py`
   - Automatically calculates optimal weights from evaluation results
   - Saves to `experiments/optimized_fusion_weights_latest.json`

## Expected Impact

### Current Fusion Performance
- **Before**: Unknown (likely worse than Jaccard alone)
- **After**: Should be closer to Jaccard (0.0833) since it's weighted 75%

### Expected P@10
- Weighted average: 0.25 × 0.0278 + 0.75 × 0.0833 = **0.0694**
- This is lower than Jaccard alone (0.0833), suggesting:
  - Embedding is actually hurting performance when combined
  - Should consider using Jaccard alone, or
  - Need better embeddings

## Next Steps

1. **Test new weights** ⏳
   - Run evaluation with new fusion weights
   - Compare to Jaccard alone
   - Verify improvement

2. **Consider Jaccard-only mode** 💡
   - Since Jaccard alone (0.0833) > Expected fusion (0.0694)
   - May want to use Jaccard as primary signal
   - Only add embedding if it improves performance

3. **Improve embedding quality** ⚠️
   - Current embedding (P@10=0.0278) is weak
   - Train better embeddings or use different methods
   - Consider higher dimensions, better hyperparameters

4. **Measure other signals** ⏳
   - Functional tags
   - Text embeddings
   - Sideboard, temporal, GNN, archetype, format
   - Once measured, re-optimize weights

## Files Updated

- `src/ml/similarity/fusion.py` - Default weights updated
- `src/ml/api/api.py` - Fallback defaults and loading logic updated
- `src/ml/scripts/update_fusion_weights_from_evaluation.py` - New optimization script
- `experiments/optimized_fusion_weights_latest.json` - Optimized weights saved

## Key Insight

**Jaccard is currently the best signal** - it outperforms embedding by 3x. The fusion weights now reflect this reality, giving Jaccard 75% weight. However, the expected fusion performance is still lower than Jaccard alone, suggesting we may want to:
- Use Jaccard as the primary/only signal for now
- Focus on improving embedding quality
- Only add embedding back when it actually helps

