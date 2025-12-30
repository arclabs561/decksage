# Execute Improvements - Step-by-Step Guide

## Quick Start

All improvement scripts are ready. Here's how to execute them in priority order.

## Phase 1: Hyperparameter Search (Highest Priority)

**Goal**: Find best embedding hyperparameters (5-7x improvement expected)

**Script**: `src/ml/scripts/improve_embeddings_hyperparameter_search.py`

**On AWS EC2** (recommended):
```bash
# Upload script and data to S3 first
aws s3 cp src/ml/scripts/improve_embeddings_hyperparameter_search.py s3://games-collections/scripts/
aws s3 cp experiments/test_set_canonical_magic.json s3://games-collections/processed/
aws s3 cp experiments/name_mapping.json s3://games-collections/processed/

# Then run on EC2 (use train_on_aws_instance.py pattern)
uv run --script src/ml/scripts/train_on_aws_instance.py \
  --script-path scripts/improve_embeddings_hyperparameter_search.py \
  --input-s3 s3://games-collections/processed/pairs_large.csv \
  --output-s3 s3://games-collections/experiments/hyperparameter_search_results.json
```

**Expected Time**: 2-4 hours (50 configs × ~3-5 min each)
**Expected Cost**: ~$0.50-1.00 (spot instance)

**Output**: `experiments/hyperparameter_search_results.json` with best configuration

## Phase 2: Expand Test Set (Can Run Locally)

**Goal**: Expand from 38 to 100+ queries

**Script**: `src/ml/scripts/improve_labeling_expand_test_set.py`

**Local**:
```bash
uv run --script src/ml/scripts/improve_labeling_expand_test_set.py \
  --input experiments/test_set_canonical_magic.json \
  --output experiments/test_set_expanded_magic.json \
  --target-size 100 \
  --batch-size 10
```

**Expected Time**: 30-60 minutes (LLM API calls)
**Expected Cost**: ~$1-2 (LLM API)

**Output**: `experiments/test_set_expanded_magic.json` with 100+ queries

## Phase 3: Enrich Graph Data (When Attributes Available)

**Goal**: Add card attributes and temporal weighting

**Script**: `src/ml/scripts/improve_data_enrich_graph.py`

**Local or AWS**:
```bash
uv run --script src/ml/scripts/improve_data_enrich_graph.py \
  --input data/processed/pairs_large.csv \
  --attributes data/processed/card_attributes.csv \
  --output-edg data/graphs/pairs_enriched.edg \
  --output-features data/graphs/node_features.json
```

**Expected Time**: 5-10 minutes
**Output**: Enriched edgelist and node features

## Phase 4: Train Improved Embeddings

**Goal**: Train with best hyperparameters and proper training loop

**Script**: `src/ml/scripts/improve_training_with_validation.py`

**On AWS EC2**:
```bash
# After hyperparameter search, use best config
uv run --script src/ml/scripts/improve_training_with_validation.py \
  --input data/graphs/pairs_enriched.edg \
  --output data/embeddings/magic_improved.wv \
  --test-set experiments/test_set_expanded_magic.json \
  --name-mapping experiments/name_mapping.json \
  --p <best_p> \
  --q <best_q> \
  --dim <best_dim> \
  --walk-length <best_walk_length> \
  --num-walks <best_num_walks> \
  --epochs 10 \
  --patience 3
```

**Expected Time**: 1-2 hours
**Expected Cost**: ~$0.25-0.50 (spot instance)

**Output**: Improved embeddings with P@10 = 0.15-0.20 (target)

## Phase 5: Evaluate and Integrate

**Goal**: Compare improved embeddings and update fusion weights

**Steps**:
1. Evaluate improved embeddings:
```bash
uv run --script src/ml/scripts/evaluate_all_embeddings.py \
  --embeddings data/embeddings/magic_improved.wv \
  --test-set experiments/test_set_expanded_magic.json \
  --name-mapping experiments/name_mapping.json
```

2. Update fusion weights:
```bash
python3 -m src.ml.scripts.update_fusion_weights_from_evaluation \
  --evaluation-results experiments/embedding_evaluation_improved.json
```

3. Test fusion with new weights:
```bash
uv run --script src/ml/scripts/test_optimized_weights.py \
  --test-set experiments/test_set_expanded_magic.json
```

**Expected Outcome**: Fusion P@10 = 0.20-0.25 (meet README goal)

## Summary

### Priority Order
1. **Hyperparameter search** (highest ROI, 5-7x improvement)
2. **Test set expansion** (better evaluation, can run in parallel)
3. **Graph enrichment** (when attributes available)
4. **Improved training** (after hyperparameter search)
5. **Evaluate and integrate** (final step)

### Expected Timeline
- **Phase 1**: 2-4 hours (AWS EC2)
- **Phase 2**: 30-60 minutes (local, parallel)
- **Phase 3**: 5-10 minutes (when ready)
- **Phase 4**: 1-2 hours (AWS EC2)
- **Phase 5**: 30 minutes (local)

**Total**: ~4-7 hours of compute time

### Expected Results
- **Embeddings**: P@10 = 0.15-0.20 (5-7x improvement)
- **Fusion**: P@10 = 0.20-0.25 (meet README goal)
- **Test Set**: 100+ queries (better evaluation)

All scripts are ready and follow research-based best practices!

