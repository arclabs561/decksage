# EC2 Spot Instance Training - In Progress

**Date**: 2025-01-27  
**Status**: 🚀 **TRAINING IN PROGRESS**

---

## Instance Details

- **Instance ID**: `i-06f00be37d6a482ff`
- **Instance Type**: `t3.medium` (spot)
- **Spot Request ID**: `sir-npwzasip`
- **State**: `running`
- **Launch Time**: 2025-12-03T07:55:39+00:00

---

## Training Configuration

- **Input**: `s3://games-collections/processed/pairs_large.csv` (265.8 MB)
- **Output**: `magic_128d_test_pecanpy.wv`
- **Dimension**: 128
- **Method**: Node2Vec via PecanPy

---

## Process

1. ✅ **Instance created** (spot instance)
2. ✅ **Instance running**
3. ⏳ **SSM agent ready** (waiting ~60 seconds)
4. ⏳ **Training in progress** (10-30 minutes expected)
5. ⏳ **Upload to S3** (automatic)
6. ⏳ **Download locally** (automatic)
7. ⏳ **Terminate instance** (with `--terminate` flag)

---

## Monitoring

Check instance status:
```bash
aws ec2 describe-instances --instance-ids i-06f00be37d6a482ff
```

Check SSM command status:
```bash
aws ssm list-commands --instance-id i-06f00be37d6a482ff
```

Check S3 for results:
```bash
aws s3 ls s3://games-collections/embeddings/magic_128d_test_pecanpy.wv
```

---

## Expected Cost

- **Spot price**: ~$0.0125/hour (70% savings vs on-demand)
- **Training time**: ~10-30 minutes
- **Estimated cost**: ~$0.003-0.006

---

**Note**: Training is running in the background. Check back in 10-30 minutes for completion.

