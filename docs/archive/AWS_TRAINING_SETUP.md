# AWS EC2 Training Setup

**Date**: 2025-01-27
**Status**: ✅ Script ready, can be used when needed

---

## Script Created

**File**: `src/ml/scripts/train_on_aws_instance.py` (PEP 723)

**Features**:
- Creates EC2 instance (or uses existing)
- **Spot instance support** (default: enabled for cost savings, 70-90% cheaper)
- **On-demand fallback** (automatic if spot request fails)
- Installs dependencies (Python 3.11, uv, pecanpy, etc.)
- Runs training via SSM
- Downloads results automatically
- Can terminate instance after training

---

## Usage

### Basic Usage
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128
```

### Use Existing Instance
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --instance-id i-1234567890abcdef0 \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d
```

### Terminate After Training
```bash
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --terminate
```

### Spot Instance Options
```bash
# Use spot instances (default, saves 70-90% on costs)
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d

# Force on-demand only (no spot)
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --no-spot

# Set custom spot max price
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --spot-max-price "0.05"

# Don't fall back to on-demand if spot fails
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --pairs-s3 s3://games-collections/processed/pairs_large.csv \
  --output magic_128d \
  --no-fallback
```

---

## Requirements

1. **AWS CLI configured** - `aws configure`
2. **EC2 permissions** - Create/terminate instances, SSM access
3. **S3 access** - Read pairs CSV, write embeddings
4. **Key pair** (optional) - For SSH access if needed

---

## Instance Configuration

- **Default type**: t3.medium
- **Pricing**: Spot instances by default (70-90% cost savings)
- **Fallback**: Automatic fallback to on-demand if spot unavailable
- **AMI**: Amazon Linux 2023 (ami-08fa3ed5577079e64 for us-east-1)
- **User data**: Installs Python 3.11, uv, dependencies
- **Tags**: Name=decksage-training, Project=decksage, InstanceType=spot/on-demand

---

## Training Process

1. Create/start EC2 instance
2. Wait for SSM agent to be ready
3. Run training script via SSM
4. Upload embeddings to S3
5. Download embeddings locally
6. (Optional) Terminate instance

---

## Cost Estimate

### On-Demand Pricing
- **t3.medium**: ~$0.0416/hour
- **Training time**: ~10-30 minutes
- **Total cost**: ~$0.01-0.02 per training run

### Spot Instance Pricing (Default)
- **t3.medium spot**: ~$0.0125/hour (70% savings)
- **Training time**: ~10-30 minutes
- **Total cost**: ~$0.003-0.006 per training run
- **Note**: Spot instances can be interrupted, but training saves to S3 automatically

---

**Status**: ✅ Ready to use when local training fails (scipy build issue)
