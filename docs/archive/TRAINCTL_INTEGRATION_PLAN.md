# trainctl Integration Plan

## Overview

Migrate all training operations to use `../trainctl` instead of custom AWS scripts.

## trainctl Capabilities

From README:
- **Multi-platform**: Local, RunPod, AWS EC2
- **Checkpoint management**: List, inspect, resume from checkpoints
- **Real-time monitoring**: Follow training logs and checkpoint progress
- **Cost optimization**: Spot instances, efficient resource usage
- **Modern tooling**: Rust CLI with `uv`, `just` integration

## Current Training Scripts to Migrate

### 1. Hyperparameter Search
- **Current**: `run_hyperparameter_search_on_aws.py`
- **New**: Use `trainctl aws train` with hyperparameter search script
- **Benefits**: Built-in monitoring, checkpoint support, spot instances

### 2. Improved Training with Validation
- **Current**: `run_improved_training_on_aws.py`
- **New**: Use `trainctl aws train` with improved training script
- **Benefits**: Checkpoint management, resume capability

### 3. Multi-Game Training
- **Current**: `train_multi_game_embeddings.py` (local only)
- **New**: Use `trainctl aws train` or `trainctl local` based on scale
- **Benefits**: Unified interface, monitoring

### 4. GNN Training
- **Current**: `train_gnn.py` (local)
- **New**: Use `trainctl runpod train` for GPU training
- **Benefits**: GPU support via RunPod, better for GNNs

## Migration Strategy

### Phase 1: Update Training Scripts
1. Ensure all training scripts are standalone (can run on remote)
2. Add checkpoint support to training scripts
3. Update scripts to use trainctl-compatible paths

### Phase 2: Create trainctl Wrappers
1. Create `justfile` recipes for common training tasks
2. Document trainctl commands for each training type
3. Test with local training first

### Phase 3: Migrate AWS Training
1. Replace `run_hyperparameter_search_on_aws.py` with trainctl
2. Replace `run_improved_training_on_aws.py` with trainctl
3. Test spot instances and monitoring

## trainctl Commands for Our Use Cases

### Hyperparameter Search
```bash
# Create AWS instance
INSTANCE_ID=$(trainctl aws create --spot --instance-type t3.medium | grep -o 'i-[a-z0-9]*')

# Train with hyperparameter search
trainctl aws train $INSTANCE_ID src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --data-s3 s3://games-collections/processed/pairs_large.csv \
    --output-s3 s3://games-collections/experiments/

# Monitor
trainctl aws monitor $INSTANCE_ID --follow
```

### Improved Training with Validation
```bash
trainctl aws train $INSTANCE_ID src/ml/scripts/improve_training_with_validation.py \
    --data-s3 s3://games-collections/graphs/pairs_enriched.edg \
    --output-s3 s3://games-collections/embeddings/
```

### Multi-Game Training
```bash
# For large-scale, use AWS
trainctl aws train $INSTANCE_ID src/ml/scripts/train_multi_game_embeddings.py \
    --data-s3 s3://games-collections/processed/pairs_multi_game.csv \
    --output-s3 s3://games-collections/embeddings/

# For testing, use local
trainctl local src/ml/scripts/train_multi_game_embeddings.py \
    --mtg-pairs data/processed/pairs_large.csv \
    --output data/embeddings/multi_game.wv
```

### GNN Training (GPU)
```bash
# Create RunPod pod with GPU
POD_ID=$(trainctl runpod create --gpu "NVIDIA GeForce RTX 4080 SUPER" | grep -o 'pod-[a-z0-9]*')

# Train GNN
trainctl runpod train $POD_ID src/ml/scripts/train_gnn.py \
    --pairs-csv data/processed/pairs_large.csv
```

## Benefits of Migration

1. **Unified Interface**: One tool for all training
2. **Better Monitoring**: Built-in log following and checkpoint tracking
3. **Cost Optimization**: Automatic spot instance handling
4. **Checkpoint Management**: Resume from failures
5. **Modern Tooling**: Rust-based, fast, reliable

## Next Steps

1. Test trainctl locally with one training script
2. Update training scripts to be trainctl-compatible
3. Create justfile recipes for common workflows
4. Migrate AWS training scripts
5. Document new workflows
