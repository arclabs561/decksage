# AWS Evaluation Script Ready ✅

## Summary

Created `src/ml/scripts/run_evaluation_on_aws.py` to run embedding evaluation on AWS EC2, bypassing local dependency issues.

## What Was Created

### Script: `run_evaluation_on_aws.py`
**Purpose**: Run `evaluate_all_embeddings.py` on AWS EC2 with proper dependencies

**Features**:
- ✅ Uploads evaluation script and name_normalizer to S3
- ✅ Creates EC2 spot instance (with on-demand fallback)
- ✅ Installs dependencies (pandas, numpy, gensim, boto3)
- ✅ Downloads test set, name mapping, embeddings, and pairs CSV from S3
- ✅ Creates standalone wrapper script to handle Python path issues
- ✅ Runs evaluation with name mapping
- ✅ Downloads results locally and uploads to S3
- ✅ Terminates instance after completion

## Usage

```bash
uv run --script src/ml/scripts/run_evaluation_on_aws.py
```

**What it does**:
1. Uploads evaluation script to S3
2. Creates EC2 instance (spot, max $0.10/hr)
3. Installs Python dependencies
4. Downloads all required data from S3
5. Runs evaluation with name mapping
6. Downloads results to `experiments/embedding_evaluation_with_mapping.json`
7. Uploads results to S3
8. Terminates instance

## Prerequisites on S3

The script expects these files to exist on S3:
- `s3://games-collections/scripts/evaluate_all_embeddings.py` (uploaded by script)
- `s3://games-collections/processed/test_set_canonical_magic.json` ✅
- `s3://games-collections/processed/name_mapping.json` ✅
- `s3://games-collections/embeddings/magic_128d_test_pecanpy.wv` ✅
- `s3://games-collections/processed/pairs_large.csv` ✅

## Expected Output

Results will be saved to:
- **Local**: `experiments/embedding_evaluation_with_mapping.json`
- **S3**: `s3://games-collections/processed/embedding_evaluation_with_mapping.json`

**Format**:
```json
{
  "magic_128d_test_pecanpy": {
    "p@10": 0.xxx,
    "mrr": 0.xxx,
    "num_queries": 36
  },
  "jaccard": {
    "p@10": 0.xxx,
    "mrr": 0.xxx,
    "num_queries": 36
  }
}
```

## Benefits

1. **Avoids Local Dependencies**: No need for pandas, numpy, gensim locally
2. **Consistent Environment**: Same Python version and dependencies every time
3. **Cost Effective**: Uses spot instances (70-90% cheaper)
4. **Automatic Cleanup**: Terminates instance after completion
5. **S3 Integration**: All data stored in S3 for easy access

## Next Steps

1. **Run the evaluation**:
   ```bash
   uv run --script src/ml/scripts/run_evaluation_on_aws.py
   ```

2. **Verify results**:
   - Check `experiments/embedding_evaluation_with_mapping.json`
   - Compare P@10 and MRR with previous results
   - Confirm name mapping fixed 0 hits issue

3. **If successful**:
   - Use results to optimize fusion weights
   - Continue with signal computation
   - Expand test sets

## Related Files

- `src/ml/scripts/evaluate_all_embeddings.py` - Main evaluation script
- `src/ml/scripts/run_name_mapping_on_aws.py` - Similar pattern for name mapping
- `src/ml/utils/name_normalizer.py` - Name mapping utilities
- `experiments/name_mapping.json` - Generated name mapping
