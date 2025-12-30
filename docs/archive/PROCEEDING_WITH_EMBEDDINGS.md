# Proceeding with Embeddings and AWS

**Date**: 2025-01-27  
**Status**: ✅ All embedding methods trained, AWS integration ready

---

## Completed

### ✅ Embedding Methods Trained

All methods successfully trained (64-dim, fast test):
- ✅ **DeepWalk** (p=1, q=1) - `data/embeddings/deepwalk.wv`
- ✅ **Node2Vec-Default** (p=1, q=1) - `data/embeddings/node2vec_default.wv`
- ✅ **Node2Vec-BFS** (p=2, q=0.5) - `data/embeddings/node2vec_bfs.wv`
- ✅ **Node2Vec-DFS** (p=0.5, q=2) - `data/embeddings/node2vec_dfs.wv`

**Graph**: 14,072 nodes, 868,336 edges

### ✅ PEP 723 Scripts

- ✅ `compare_embedding_methods.py` - Compare all methods
- ✅ `train_all_embeddings.py` - Train and upload to S3
- ✅ `train_with_aws.py` - AWS-backed training
- ✅ `aws_data_ops.py` - S3 operations

---

## Current State

### Graph Embedding Methods

**Classical (Still Competitive)**:
- **DeepWalk** - Simple baseline
- **Node2Vec** - Configurable p, q
- **Node2Vec-BFS** - Local structure (p=2, q=0.5)
- **Node2Vec-DFS** - Communities (p=0.5, q=2)

**Modern (2024-2025)**:
- **Graph NE** - Simpler, no hyperparameter tuning (research needed)
- **Meta Node2Vec** - Heterogeneous graphs (format/archetype metadata)
- **PyTorch Geometric Node2Vec** - GPU-accelerated, integrates with GNNs

**GNNs**:
- **GraphSAGE** - Best for co-occurrence graphs (PyTorch Geometric)
- **GCN, GAT** - Alternative architectures

---

## What We're Using

### Primary: PecanPy (Node2Vec)
- Fast, parallelized
- Supports weighted graphs
- Multiple modes (PreComp, SparseOTF, DenseOTF)
- File: `src/ml/similarity/card_similarity_pecan.py`

### Secondary: PyTorch Geometric
- For GNNs (GraphSAGE, GCN, GAT)
- Also has Node2Vec (GPU-accelerated)
- File: `src/ml/similarity/gnn_embeddings.py`
- Status: Code ready, blocked by scipy build

---

## Next Steps

### Immediate
1. ✅ Train all embedding variants - **DONE**
2. ⏳ Compare performance on test set
3. ⏳ Upload to S3
4. ⏳ Measure individual signal performance

### Future
1. **Graph NE** - Research and implement
2. **Meta Node2Vec** - Use format/archetype metadata
3. **PyG Node2Vec** - GPU-accelerated alternative
4. **GNN Training** - Once scipy issue resolved or on AWS

---

## Usage

### Compare Methods (PEP 723)
```bash
uv run --script src/ml/scripts/compare_embedding_methods.py \
  --input data/processed/pairs_large.csv \
  --methods deepwalk node2vec node2vec_bfs node2vec_dfs \
  --dim 128
```

### Train and Upload to S3
```bash
uv run --script src/ml/scripts/train_all_embeddings.py \
  --input data/processed/pairs_large.csv \
  --dim 128 \
  --upload
```

### Train on AWS
```bash
uv run --script src/ml/scripts/train_with_aws.py \
  --pairs-csv data/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128 \
  --upload
```

---

## Files

- `src/ml/scripts/compare_embedding_methods.py` - PEP 723 comparison
- `src/ml/scripts/train_all_embeddings.py` - Train and upload
- `src/ml/scripts/train_with_aws.py` - AWS-backed training
- `src/ml/scripts/aws_data_ops.py` - S3 operations
- `GRAPH_EMBEDDING_METHODS.md` - Research summary
- `EMBEDDING_METHODS_COMPLETE.md` - Status

---

**Status**: ✅ All methods trained, ready for evaluation and S3 upload

