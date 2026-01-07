# Future Training: Use runctl

For future game-specific embedding training, use `runctl` instead of direct execution:

## Benefits:
- AWS/RunPod execution (better resources)
- Automatic checkpointing and resume
- S3 integration for data/artifacts
- Better monitoring and logging
- Cost optimization (spot instances)

## Example Commands:

```bash
# Train Magic embeddings on AWS
runctl aws create --instance-type t3.large \
  --script src/ml/scripts/train_game_specific_embeddings.py \
  --args "--input s3://games-collections/processed/pairs_large.csv --output s3://games-collections/embeddings/magic_game_specific.wv --game magic --dim 128 --epochs 50" \
  --data-s3 s3://games-collections/processed/ \
  --output-s3 s3://games-collections/embeddings/

# Train Pokemon/Yu-Gi-Oh on AWS (when data available)
runctl aws create --instance-type t3.large \
  --script src/ml/scripts/train_game_specific_embeddings.py \
  --args "--input s3://games-collections/processed/pairs_multi_game.csv --output s3://games-collections/embeddings/pokemon_game_specific.wv --game pokemon --dim 128 --epochs 50" \
  --data-s3 s3://games-collections/processed/ \
  --output-s3 s3://games-collections/embeddings/
```

## Current Status:
- Current training: Running locally (will complete)
- Future training: Should use runctl for better resource management
