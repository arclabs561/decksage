# AimStack Quick Start Guide

## Installation Status
✅ **Installed**: AimStack 3.29.1  
✅ **Repository**: Initialized at `.aim/`  
✅ **Integration**: Complete in all scripts

## Quick Commands

### Launch UI
```bash
uv run aim up
```
Access at: http://localhost:43800

### View Runs
```bash
uv run aim runs list
```

### Query Runs
```bash
# List experiments
uv run aim runs list --experiment embedding_training

# Filter by tags
uv run aim runs list --tag node2vec
```

## Integrated Scripts

All these scripts now track to AimStack:

1. **Training**: `src/ml/scripts/improve_training_with_validation_enhanced.py`
   - Tracks: loss, P@10, learning rate per epoch
   - Experiment: `embedding_training`

2. **Hyperparameter Search**: `src/ml/scripts/improve_embeddings_hyperparameter_search.py`
   - Tracks: P@10, MRR, nDCG for each configuration
   - Experiment: `hyperparameter_search`

3. **Evaluation**: `src/ml/scripts/evaluate_all_embeddings.py`
   - Tracks: P@10, MRR for each embedding method
   - Experiment: `embedding_evaluation`

## Usage Example

### Run Training with Tracking
```bash
uv run src/ml/scripts/improve_training_with_validation_enhanced.py \
    --input data/processed/pairs_large.csv \
    --output data/embeddings/trained.wv \
    --dim 128 \
    --walk-length 80 \
    --num-walks 10 \
    --window-size 10 \
    --p 1.0 \
    --q 1.0 \
    --epochs 10 \
    --val-ratio 0.1 \
    --patience 3 \
    --lr 0.025 \
    --lr-decay 0.95
```

Then view results:
```bash
uv run aim up
```

## Helper Functions

Available in `src/ml/utils/aim_helpers.py`:

- `create_training_run()` - Create a new Aim run
- `track_training_metrics()` - Track training metrics
- `track_evaluation_metrics()` - Track evaluation metrics
- `track_hyperparameter_result()` - Track hyperparameter search results
- `track_artifact()` - Track files/artifacts

## Best Practices

1. **Consistent Naming**: Use consistent experiment names
2. **Tags**: Use tags to organize runs (e.g., "node2vec", "baseline")
3. **Context**: Use context to group related metrics
4. **Artifacts**: Track important files (embeddings, checkpoints)

## Next Steps

1. Run your next training/evaluation
2. Launch Aim UI: `uv run aim up`
3. Compare experiments visually
4. Use AimQL to query and filter runs

