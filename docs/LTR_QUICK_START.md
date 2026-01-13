# Learning-to-Rank Quick Start Guide

**Date:** January 6, 2026

## Overview

The LTR pipeline separates feature extraction from reranking, enabling learned optimal combination of similarity signals.

## Quick Start

### 1. Train a Reranker

```bash
python scripts/optimization/train_reranker.py \
    --test-set experiments/test_set_unified_magic.json \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --output models/reranker.pkl \
    --method lightgbm
```

### 2. Evaluate Reranker

```bash
python scripts/evaluation/evaluate_reranker.py \
    --test-set experiments/test_set_unified_magic.json \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --reranker-model models/reranker.pkl \
    --top-k 10
```

### 3. Use in API

```bash
# Set environment variable
export RERANKER_PATH=models/reranker.pkl

# API will automatically use two-stage pipeline
# Stage 1: Fast retrieval (manual fusion, top 100)
# Stage 2: Learned reranking (top 10)
```

## Architecture

```
Query → Feature Extraction → Learned Reranker → Results
         [47+ features]      [LightGBM/XGBoost]
```

## Features Extracted

- **Similarity scores**: embed, jaccard, text_embed, visual_embed, gnn, etc.
- **Rank positions**: embed_rank, jaccard_rank, etc.
- **Aggregation**: max, min, mean, variance, range
- **Query context**: cmc, type, colors
- **Candidate context**: cmc, type, colors
- **Interactions**: cmc_diff, same_type, same_colors
- **Agreement**: cross-modal agreement features

## Benefits

- ✅ Learns optimal combination from labeled data
- ✅ Can learn feature interactions
- ✅ Non-linear relationships
- ✅ Query-dependent adaptation
- ✅ Better quality than manual fusion (once trained)

## See Also

- `docs/LTR_CRITIQUE_AND_REFINEMENT.md` - Detailed analysis
- `docs/FEATURES_TO_RERANK_ARCHITECTURE.md` - Architecture design
- `docs/LTR_IMPLEMENTATION_COMPLETE.md` - Implementation details
