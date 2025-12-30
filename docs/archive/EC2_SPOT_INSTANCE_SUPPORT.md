# EC2 Spot Instance Support

**Date**: 2025-01-27  
**Status**: ✅ Complete - Spot and on-demand instances now supported

---

## Summary

Updated `src/ml/scripts/train_on_aws_instance.py` to support both EC2 spot instances (for cost savings) and on-demand instances (for reliability), with automatic fallback.

---

## Features Added

### 1. Spot Instance Support (Default)
- **Cost savings**: 70-90% cheaper than on-demand
- **Automatic fallback**: Falls back to on-demand if spot request fails
- **Configurable max price**: Set custom spot price limits
- **Interruption handling**: Detects and reports spot interruptions

### 2. On-Demand Support
- **Reliability**: Always available, no interruptions
- **Fallback option**: Used automatically if spot fails (unless `--no-fallback`)

### 3. New Command-Line Options

```bash
--no-spot              # Force on-demand only (no spot)
--spot-max-price PRICE # Set maximum spot price per hour
--no-fallback          # Don't fall back to on-demand if spot fails
```

---

## Usage Examples

### Default (Spot with On-Demand Fallback)
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d
```

### Force On-Demand Only
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --no-spot
```

### Custom Spot Max Price
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --spot-max-price "0.05"
```

### No Fallback (Fail if Spot Unavailable)
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --no-fallback
```

---

## Cost Comparison

### On-Demand (t3.medium)
- **Price**: ~$0.0416/hour
- **Training time**: 10-30 minutes
- **Cost per run**: ~$0.01-0.02

### Spot Instance (t3.medium)
- **Price**: ~$0.0125/hour (70% savings)
- **Training time**: 10-30 minutes
- **Cost per run**: ~$0.003-0.006
- **Savings**: ~70% compared to on-demand

---

## Implementation Details

### Spot Instance Request
- **Market type**: Spot
- **Spot type**: one-time (not persistent)
- **Interruption behavior**: terminate (saves to S3 automatically)
- **Max price**: Configurable, defaults to reasonable price

### Fallback Logic
1. Try spot instance first (if `--no-spot` not specified)
2. If spot request fails, automatically try on-demand
3. If `--no-fallback` specified, fail instead of falling back

### Instance Tagging
- **InstanceType**: "spot" or "on-demand" tag added for tracking
- **Name**: "decksage-training"
- **Project**: "decksage"

---

## Spot Instance Considerations

### Advantages
- **Cost savings**: 70-90% cheaper
- **Same performance**: Same instance types, same compute
- **Automatic fallback**: Falls back to on-demand if needed

### Disadvantages
- **Interruptions**: Can be terminated with 2-minute warning
- **Availability**: May not be available in all regions/zones
- **No guarantee**: Not suitable for time-critical workloads

### Mitigation
- **S3 auto-save**: Training saves to S3 automatically
- **Checkpointing**: Can resume from checkpoints if interrupted
- **Fallback**: Automatic fallback to on-demand

---

## Status

✅ **Complete**: Spot and on-demand instances fully supported  
✅ **Tested**: Ready for use  
✅ **Documented**: Usage examples and cost comparison included

---

**Next Steps**: Use spot instances by default for training to save costs while maintaining reliability through automatic fallback.

