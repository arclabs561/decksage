# Visual Embeddings: Evaluation Guide

**Date**: January 2026

## Overview

This guide explains how to evaluate the impact of visual embeddings on similarity search quality.

## Quick Evaluation

### 1. Compare With/Without Visual Embeddings

```bash
# Run evaluation comparing with and without visual embeddings
./scripts/evaluation/run_visual_embeddings_evaluation.sh
```

Or manually:
```bash
python3 scripts/evaluation/evaluate_visual_embeddings.py \
    --test-set data/test_set_minimal.json \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/pairs/magic_large.csv \
    --top-k 10 \
    --output experiments/visual_embeddings_evaluation.json
```

**Expected Output**:
- P@10 with visual embeddings
- P@10 without visual embeddings
- Improvement (absolute and relative %)

### 2. Ablation Study

Measure contribution at different weight levels:

```bash
python3 scripts/evaluation/visual_embeddings_ablation.py \
    --test-set data/test_set_minimal.json \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/pairs/magic_large.csv \
    --weights 0.0 0.10 0.20 0.30 0.40 \
    --top-k 10 \
    --output experiments/visual_embeddings_ablation.json
```

**Expected Output**:
- P@10 at each visual weight level
- Best weight identification
- Performance curve

### 3. Coverage Analysis

Analyze image URL coverage:

```bash
python3 scripts/analysis/visual_embedding_coverage.py \
    --all-games \
    --output experiments/visual_coverage_analysis.json
```

**Expected Output**:
- Coverage % per game
- Cards missing images
- Prioritization for image collection

## Evaluation Metrics

### Primary Metrics

- **P@10**: Precision at 10 (most important)
- **NDCG@10**: Normalized Discounted Cumulative Gain
- **Recall@10**: Recall at 10
- **MRR**: Mean Reciprocal Rank

### Interpretation

- **P@10 > 0.15**: Good performance
- **P@10 improvement > 5%**: Visual embeddings are helping
- **P@10 improvement < 2%**: Visual embeddings may not be worth the cost

## Optimization

### Optimize Fusion Weights with Visual Embeddings

```bash
python3 scripts/optimization/optimize_fusion_with_visual.py \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/pairs/magic_large.csv \
    --test-set data/test_set_minimal.json \
    --top-k 10 \
    --output experiments/optimized_weights_with_visual.json
```

This will find optimal weights including visual embeddings.

## Downstream Task Evaluation

### Substitution Task

Visual embeddings should help identify:
- Reprints (same card, different set)
- Alternate art versions
- Visually similar cards

```bash
# Run downstream evaluation with visual embeddings enabled
python3 src/ml/scripts/evaluate_downstream_complete.py \
    --game magic \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/pairs/magic_large.csv
```

### Deck Completion

Visual embeddings may help with:
- Identifying cards that "look right" for a deck theme
- Finding visually cohesive card sets

## Troubleshooting

### Low Coverage

If coverage is low (<50%):
- Check card data format
- Verify image URL fields
- Run `collect_card_images.py` to download images

### No Improvement

If visual embeddings don't improve P@10:
- Check if test set includes visual similarity cases (reprints, alternates)
- Verify visual embedder is actually being used (check logs)
- Try different visual weight (ablation study)

### Performance Issues

If evaluation is slow:
- Visual embeddings are cached (first run downloads images)
- Subsequent runs use cached embeddings
- Consider reducing test set size for quick iteration

## Next Steps After Evaluation

1. **If improvement > 5%**: 
   - Optimize weights based on results
   - Consider fine-tuning on card images
   - Deploy to production

2. **If improvement < 2%**:
   - Review test set (may not include visual cases)
   - Check image quality/coverage
   - Consider different visual model

3. **If no improvement**:
   - Verify visual embedder is working (run validation script)
   - Check if cards have image URLs
   - Review fusion weights (visual_embed may be too low)

