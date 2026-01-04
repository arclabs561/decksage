# Continuing After Evaluation - Progress Update

## ✅ Completed This Session

### 1. Evaluation with Name Mapping ✅
- **Ran full evaluation on AWS EC2**
- **Results**: Jaccard (P@10=0.0833) outperforms embedding (P@10=0.0278) by 3x
- **Name mapping fixed 0 hits issue**: 36/38 queries evaluated (94.7% coverage)
- **Results saved**: `experiments/embedding_evaluation_with_mapping.json` and S3

### 2. Fusion Weight Optimization ✅
- **Calculated optimal weights** based on evaluation results:
  - embed: 0.25 (25%)
  - jaccard: 0.75 (75%)
  - functional: 0.0 (0% - not measured)
- **Updated defaults** in `src/ml/similarity/fusion.py`
- **Updated API** to load optimized weights from `optimized_fusion_weights_latest.json`
- **Created script**: `src/ml/scripts/update_fusion_weights_from_evaluation.py`

### 3. Key Findings
- **Jaccard is the best signal** (3x better than embedding)
- **Current embedding quality is weak** (P@10=0.0278)
- **Fusion expected performance**: 0.0694 (lower than Jaccard alone)
- **Recommendation**: Consider using Jaccard as primary signal, or improve embeddings

## 🎯 Next Steps

### Immediate (High Priority)

1. **Test New Fusion Weights** ⏳
   - Run evaluation with updated weights
   - Verify improvement over previous fusion
   - Compare to Jaccard alone

2. **Improve Embedding Quality** ⚠️
   - Current embedding (P@10=0.0278) is weak
   - Options:
     - Train better embeddings (more dimensions, better hyperparameters)
     - Try different embedding methods (DeepWalk, Node2Vec variants)
     - Use more training data

3. **Measure Other Signals** ⏳
   - Functional tags
   - Text embeddings
   - Sideboard, temporal, GNN, archetype, format
   - Once measured, re-optimize weights

### Medium Priority

4. **Compute All Signals** ⏳
   - Sideboard co-occurrence
   - Temporal trends
   - Archetype staples
   - Format patterns
   - **Blocked by**: Need decks metadata

5. **Export Decks Metadata** ⏳
   - Check S3 for `decks_with_metadata.jsonl`
   - If missing, generate on AWS EC2
   - Required for signal computation

6. **Train GNN Models** ⏳
   - May improve embeddings
   - Use AWS EC2 with GPU if needed
   - **Blocked by**: PyTorch dependencies

### Long-Term

7. **Expand Test Sets**
   - Current: 38 queries (94.7% coverage)
   - Target: 50-100 queries per game
   - Use LLM-as-Judge to generate more

8. **Temporal Evaluation**
   - Implement temporal context capture
   - Evaluate with time awareness
   - Track format rotations and ban timeline

## 📊 Current Performance Baseline

| Method | P@10 | MRR | Status |
|--------|------|-----|--------|
| **Jaccard** | **0.0833** | **0.0472** | ✅ Best |
| Embedding | 0.0278 | 0.0278 | ⚠️ Weak |
| Fusion (expected) | 0.0694 | - | ⏳ To test |

## 🔍 Key Insights

1. **Name normalization was critical** - Fixed 0 hits issue
2. **Jaccard outperforms embedding** - 3x better performance
3. **Current embedding needs improvement** - P@10=0.0278 is low
4. **Fusion may not help yet** - Expected performance (0.0694) < Jaccard alone (0.0833)

## 💡 Recommendations

1. **Short-term**: Use Jaccard as primary signal (it's the best we have)
2. **Medium-term**: Improve embedding quality before adding to fusion
3. **Long-term**: Measure all signals and optimize weights holistically

## Files Updated

- `src/ml/similarity/fusion.py` - Default weights updated
- `src/ml/api/api.py` - Loading logic updated
- `src/ml/scripts/update_fusion_weights_from_evaluation.py` - New script
- `experiments/optimized_fusion_weights_latest.json` - Optimized weights
- `FUSION_WEIGHTS_UPDATED.md` - Documentation

## Ready to Continue

All infrastructure is in place. Next actions:
1. Test new fusion weights
2. Improve embedding quality
3. Measure other signals
4. Compute all signals (when decks metadata available)
