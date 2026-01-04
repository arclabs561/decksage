# Evaluation Results with Name Mapping ✅

## Summary

Successfully ran evaluation on AWS EC2 with name mapping. **Name normalization fixed the 0 hits issue!**

## Results

### Metrics

| Method | P@10 | MRR | Queries Evaluated |
|--------|------|-----|-------------------|
| **Jaccard** | **0.0833** | **0.0472** | 36 |
| magic_128d_test_pecanpy | 0.0278 | 0.0278 | 36 |

### Key Findings

1. **✅ Name Mapping Works!**
   - **Before**: 0 hits (name mismatches)
   - **After**: 36 queries evaluated successfully
   - Name normalization successfully resolved the critical blocker

2. **Jaccard Outperforms Embedding**
   - Jaccard: P@10 = 0.0833, MRR = 0.0472
   - Embedding: P@10 = 0.0278, MRR = 0.0278
   - **Jaccard is 3x better** than the current embedding

3. **Query Coverage**
   - 36 out of 38 queries evaluated (94.7% coverage)
   - 2 queries missing: "Delver of Secrets", "Orcish Bowmasters" (not in embeddings/graph)

## Analysis

### Why is Jaccard Better?

Possible reasons:
1. **Embedding quality**: The current embedding (`magic_128d_test_pecanpy`) may not be well-trained
2. **Test set bias**: Test set might favor co-occurrence patterns (which Jaccard captures directly)
3. **Embedding dimension**: 128 dimensions might be insufficient
4. **Training data**: Embedding might need more training data or better hyperparameters

### Next Steps

1. **Improve Embedding Quality** ⚠️
   - Train better embeddings (more dimensions, better hyperparameters)
   - Try different embedding methods (DeepWalk, Node2Vec variants)
   - Use more training data

2. **Investigate Jaccard Performance** ✅
   - Jaccard is working well - this is good news!
   - Consider using Jaccard as a stronger signal in fusion

3. **Optimize Fusion Weights**
   - Current fusion likely underweights Jaccard
   - Should increase Jaccard weight given its superior performance

4. **Expand Test Set**
   - Add more queries for better evaluation coverage
   - Include diverse card types and formats

## Files

- **Results**: `experiments/embedding_evaluation_with_mapping.json`
- **S3**: `s3://games-collections/processed/embedding_evaluation_with_mapping.json`
- **Name Mapping**: `experiments/name_mapping.json`

## Impact

### Before Name Mapping
- ❌ 0 hits (name mismatches)
- ❌ Could not evaluate any queries
- ❌ No meaningful metrics

### After Name Mapping
- ✅ 36 queries evaluated (94.7% coverage)
- ✅ Meaningful metrics obtained
- ✅ Can now compare methods accurately
- ✅ Identified that Jaccard outperforms current embedding

## Recommendations

1. **Immediate**: Increase Jaccard weight in fusion (it's 3x better!)
2. **Short-term**: Train better embeddings or use existing better embeddings
3. **Medium-term**: Expand test set for more comprehensive evaluation
4. **Long-term**: Optimize fusion weights based on individual signal performance

## Conclusion

**Name normalization was a critical fix** - it enabled proper evaluation and revealed important insights:
- Jaccard is currently the best performing method
- Current embedding needs improvement
- Fusion weights should be adjusted to favor Jaccard
