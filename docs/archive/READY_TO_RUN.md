# Ready to Run - Evaluation with Name Mapping

## ✅ What's Ready

### 1. Name Mapping ✅
- **File**: `experiments/name_mapping.json`
- **S3**: `s3://games-collections/processed/name_mapping.json`
- **Status**: Generated and ready to use

### 2. AWS Evaluation Script ✅
- **File**: `src/ml/scripts/run_evaluation_on_aws.py`
- **Status**: Complete and ready to execute
- **Features**:
  - Handles all dependencies automatically
  - Downloads data from S3
  - Runs evaluation with name mapping
  - Downloads results locally
  - Uploads results to S3

### 3. Evaluation Script ✅
- **File**: `src/ml/scripts/evaluate_all_embeddings.py`
- **Status**: Updated with name mapping support
- **Features**:
  - Supports name mapping for embeddings
  - Supports name mapping for Jaccard
  - Handles missing mappings gracefully

## 🚀 Run Evaluation Now

```bash
uv run --script src/ml/scripts/run_evaluation_on_aws.py
```

**What it does**:
1. Uploads evaluation script to S3
2. Creates EC2 spot instance (t3.medium, ~$0.01/hr)
3. Installs Python dependencies
4. Downloads test set, name mapping, embeddings, pairs CSV
5. Runs evaluation with name mapping
6. Downloads results to `experiments/embedding_evaluation_with_mapping.json`
7. Uploads results to S3
8. Terminates instance

**Expected Time**: 10-15 minutes  
**Expected Cost**: ~$0.01-0.02

## 📊 Expected Results

The evaluation will produce metrics for:
- `magic_128d_test_pecanpy` embedding
- Jaccard baseline

**Metrics**:
- **P@10**: Precision at 10 (higher is better)
- **MRR**: Mean Reciprocal Rank (higher is better)
- **num_queries**: Number of queries evaluated

**Expected Improvement**:
- **Before name mapping**: 0 hits (name mismatches)
- **After name mapping**: Should see actual hits and meaningful metrics

## 📁 Output Files

- **Local**: `experiments/embedding_evaluation_with_mapping.json`
- **S3**: `s3://games-collections/processed/embedding_evaluation_with_mapping.json`

## 🔍 What to Check After Running

1. **Results file exists**: `experiments/embedding_evaluation_with_mapping.json`
2. **Metrics are reasonable**: P@10 > 0, MRR > 0
3. **Name mapping worked**: Compare with previous 0 hits
4. **All methods evaluated**: Check that both embedding and Jaccard ran

## 🎯 Next Steps After Evaluation

1. **Analyze results**: Compare embedding vs Jaccard performance
2. **Optimize fusion weights**: Use results to improve fusion
3. **Expand test set**: Add more queries for better coverage
4. **Compute signals**: If decks metadata available, compute all signals

## 💡 Tips

- **Monitor progress**: The script prints progress at each step
- **Check S3**: Results are also uploaded to S3 automatically
- **Instance cleanup**: Instance is terminated automatically
- **Cost tracking**: Spot instances are very cheap (~$0.01/hr)

## 🐛 Troubleshooting

If evaluation fails:
1. Check S3 for required files (test set, name mapping, embeddings, pairs CSV)
2. Check instance logs in AWS Console
3. Verify IAM role has S3 read permissions
4. Check that dependencies installed correctly

## Related Files

- `src/ml/scripts/run_evaluation_on_aws.py` - AWS orchestration script
- `src/ml/scripts/evaluate_all_embeddings.py` - Main evaluation script
- `src/ml/utils/name_normalizer.py` - Name mapping utilities
- `experiments/name_mapping.json` - Generated name mapping

