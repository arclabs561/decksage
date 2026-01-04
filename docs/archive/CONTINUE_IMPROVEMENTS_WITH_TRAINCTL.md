# Continue All Improvements with trainctl

## Current Status

### ✅ Completed
- **Test Set**: 100 queries (target reached)
- **Labeling**: All 100 queries now have labels
- **Graph Enrichment**: Complete
- **Multi-Game Training**: Scripts ready

### ⚠️ Issues Found
- **Hyperparameter Search**: Results not found (may need to re-run)
- **Card Attributes**: CSV has rows but many appear empty (need verification)

## Strategy: Use trainctl for All Training

### Why trainctl?
- **Unified interface**: One tool for local, AWS, RunPod
- **Better monitoring**: Built-in log following
- **Checkpoint management**: Resume from failures
- **Cost optimization**: Automatic spot instance handling
- **Modern tooling**: Rust-based, fast, reliable

## Next Steps with trainctl

### 1. Re-run Hyperparameter Search (if needed)
```bash
# Using trainctl
trainctl aws create --spot --instance-type t3.medium
trainctl aws train <instance-id> src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --data-s3 s3://games-collections/processed/pairs_large.csv \
    --output-s3 s3://games-collections/experiments/
```

### 2. Train Improved Embeddings
```bash
# After getting best hyperparameters
trainctl aws train <instance-id> src/ml/scripts/improve_training_with_validation.py \
    --data-s3 s3://games-collections/graphs/pairs_enriched.edg \
    --output-s3 s3://games-collections/embeddings/
```

### 3. Multi-Game Training
```bash
# Export multi-game graph first
go run src/backend/cmd/export-multi-game-graph/main.go data-full data/processed/pairs_multi_game.csv

# Then train with trainctl
trainctl aws train <instance-id> src/ml/scripts/train_multi_game_embeddings.py \
    --data-s3 s3://games-collections/processed/pairs_multi_game.csv \
    --output-s3 s3://games-collections/embeddings/
```

## Immediate Actions

1. **Verify card enrichment** - Check actual enrichment status
2. **Find/re-run hyperparameter search** - Critical for next training
3. **Continue card enrichment** - Scale to all cards if needed
4. **Test trainctl locally** - Verify it works before AWS
5. **Train with best config** - Once hyperparameters found

## trainctl Integration Status

- ✅ Integration plan created
- ✅ justfile recipes created
- 🔄 trainctl compiling
- ⏳ Need to test locally first
- ⏳ Then migrate AWS scripts
