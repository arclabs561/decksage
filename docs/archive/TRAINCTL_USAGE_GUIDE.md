# trainctl Usage Guide for DeckSage

## Overview

`trainctl` is a Rust-based CLI for modern training orchestration, supporting:
- **Local training**: Run scripts locally with monitoring
- **AWS EC2**: Spot and on-demand instances with automatic fallback
- **RunPod**: GPU training support
- **Checkpoint management**: List, inspect, resume from checkpoints
- **Real-time monitoring**: Follow training logs and checkpoint progress

## Building trainctl

```bash
cd ../trainctl
cargo build --release
# Binary at: ../trainctl/target/release/trainctl
```

## Training Scripts Compatible with trainctl

### Requirements
1. **Standalone**: Scripts must work without external module dependencies (or handle imports)
2. **Checkpoint support**: Save progress periodically
3. **Progress logging**: Clear progress indicators
4. **Error handling**: Graceful failure with resume capability

### Our Compatible Scripts
- ✅ `improve_training_with_validation_enhanced.py` - Enhanced training with validation
- ✅ `improve_embeddings_hyperparameter_search.py` - Hyperparameter search
- ✅ `train_multi_game_embeddings.py` - Multi-game training
- ⏳ `improve_training_with_validation.py` - Needs checkpoint support

## Local Training

### Basic Usage
```bash
# Set trainctl path
export TRAINCTL_BIN="../trainctl/target/release/trainctl"

# Train locally
$TRAINCTL_BIN local src/ml/scripts/improve_training_with_validation_enhanced.py \
    --input data/processed/pairs_large.csv \
    --output data/embeddings/trained.wv \
    --dim 128 \
    --walk-length 80 \
    --num-walks 10
```

### With Wrapper Script
```bash
# Use our wrapper
./src/ml/scripts/train_with_trainctl.sh \
    --input data/processed/pairs_large.csv \
    --output data/embeddings/trained.wv
```

## AWS EC2 Training

### Create Instance
```bash
# Spot instance (cheaper)
INSTANCE_ID=$($TRAINCTL_BIN aws create --spot --instance-type t3.medium | grep -o 'i-[a-z0-9]*')

# On-demand (more reliable)
INSTANCE_ID=$($TRAINCTL_BIN aws create --instance-type t3.medium | grep -o 'i-[a-z0-9]*')
```

### Train on AWS
```bash
# Upload and train
$TRAINCTL_BIN aws train $INSTANCE_ID \
    src/ml/scripts/improve_training_with_validation_enhanced.py \
    --input s3://games-collections/processed/pairs_large.csv \
    --output s3://games-collections/embeddings/trained.wv \
    --dim 128 \
    --walk-length 80
```

### Monitor Training
```bash
# Follow logs
$TRAINCTL_BIN aws monitor $INSTANCE_ID --follow

# List checkpoints
$TRAINCTL_BIN aws checkpoints $INSTANCE_ID
```

## Hyperparameter Search with trainctl

### Local (Small Search)
```bash
$TRAINCTL_BIN local src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --input data/processed/pairs_large.csv \
    --test-set experiments/test_set_labeled_magic.json \
    --output experiments/hyperparameter_results.json
```

### AWS (Large Search)
```bash
# Create instance
INSTANCE_ID=$($TRAINCTL_BIN aws create --spot --instance-type g4dn.xlarge)

# Run search
$TRAINCTL_BIN aws train $INSTANCE_ID \
    src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --input s3://games-collections/processed/pairs_large.csv \
    --test-set s3://games-collections/processed/test_set_labeled_magic.json \
    --output s3://games-collections/experiments/hyperparameter_results.json

# Monitor
$TRAINCTL_BIN aws monitor $INSTANCE_ID --follow
```

## Multi-Game Training

### Export Graph First
```bash
./bin/export-multi-game-graph data-full data/processed/pairs_multi_game.csv
```

### Train with trainctl
```bash
# Local (testing)
$TRAINCTL_BIN local src/ml/scripts/train_multi_game_embeddings.py \
    --input data/processed/pairs_multi_game.csv \
    --output data/embeddings/multi_game_unified.wv \
    --mode unified

# AWS (production)
INSTANCE_ID=$($TRAINCTL_BIN aws create --spot --instance-type t3.large)
$TRAINCTL_BIN aws train $INSTANCE_ID \
    src/ml/scripts/train_multi_game_embeddings.py \
    --input s3://games-collections/processed/pairs_multi_game.csv \
    --output s3://games-collections/embeddings/multi_game_unified.wv \
    --mode unified
```

## Checkpoint Management

### List Checkpoints
```bash
# Local
$TRAINCTL_BIN local checkpoints

# AWS
$TRAINCTL_BIN aws checkpoints $INSTANCE_ID
```

### Resume from Checkpoint
```bash
# Local
$TRAINCTL_BIN local resume <checkpoint-id>

# AWS
$TRAINCTL_BIN aws resume $INSTANCE_ID <checkpoint-id>
```

## Best Practices

### 1. Use Spot Instances for Long Jobs
```bash
# trainctl handles spot interruptions automatically
INSTANCE_ID=$($TRAINCTL_BIN aws create --spot --instance-type t3.medium)
```

### 2. Monitor Training Progress
```bash
# Always monitor long-running jobs
$TRAINCTL_BIN aws monitor $INSTANCE_ID --follow
```

### 3. Save Checkpoints Frequently
- Training scripts should save checkpoints every N epochs
- Use `--checkpoint-dir` to specify checkpoint location
- trainctl will track and manage checkpoints automatically

### 4. Use S3 for Data and Outputs
```bash
# Input from S3
--input s3://games-collections/processed/pairs_large.csv

# Output to S3
--output s3://games-collections/embeddings/trained.wv
```

## Integration with justfile

Add to `justfile`:
```justfile
# Build trainctl
trainctl-build:
    cd ../trainctl && cargo build --release

# Train locally
train-local:
    ../trainctl/target/release/trainctl local src/ml/scripts/improve_training_with_validation_enhanced.py \
        --input data/processed/pairs_large.csv \
        --output data/embeddings/trained.wv

# Train on AWS
train-aws instance:
    ../trainctl/target/release/trainctl aws train {{instance}} \
        src/ml/scripts/improve_training_with_validation_enhanced.py \
        --input s3://games-collections/processed/pairs_large.csv \
        --output s3://games-collections/embeddings/trained.wv

# Hyperparameter search
hyperparam-search:
    ../trainctl/target/release/trainctl aws create --spot --instance-type g4dn.xlarge | \
        xargs -I {} ../trainctl/target/release/trainctl aws train {} \
            src/ml/scripts/improve_embeddings_hyperparameter_search.py \
            --input s3://games-collections/processed/pairs_large.csv \
            --test-set s3://games-collections/processed/test_set_labeled_magic.json \
            --output s3://games-collections/experiments/hyperparameter_results.json
```

## Migration from Custom AWS Scripts

### Old Way (Custom Script)
```bash
python src/ml/scripts/run_hyperparameter_search_on_aws.py
```

### New Way (trainctl)
```bash
INSTANCE_ID=$($TRAINCTL_BIN aws create --spot --instance-type g4dn.xlarge)
$TRAINCTL_BIN aws train $INSTANCE_ID \
    src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --input s3://games-collections/processed/pairs_large.csv \
    --output s3://games-collections/experiments/hyperparameter_results.json
$TRAINCTL_BIN aws monitor $INSTANCE_ID --follow
```

**Benefits**:
- Unified interface (local, AWS, RunPod)
- Built-in monitoring
- Automatic checkpoint management
- Spot instance handling
- Modern Rust-based tooling

