# Embedding Methods: Complete Status

**Date**: 2025-01-27  
**Status**: ✅ DeepWalk trained, comparison script ready

---

## Current State

### What We're Using

1. **PecanPy (Node2Vec)** - Primary method
   - Fast, parallelized implementation
   - Supports weighted graphs (node2vec+)
   - File: `src/ml/similarity/card_similarity_pecan.py`

2. **PyTorch Geometric** - For GNNs
   - GraphSAGE, GCN, GAT models
   - File: `src/ml/similarity/gnn_embeddings.py`
   - Status: Code ready, blocked by scipy build

---

## Methods Comparison

### Classical Methods (Still Competitive)

| Method | p | q | Description | Status |
|--------|---|---|-------------|--------|
| **DeepWalk** | 1.0 | 1.0 | Unbiased random walks | ✅ Trained |
| **Node2Vec-Default** | 1.0 | 1.0 | Same as DeepWalk | ⏳ Training |
| **Node2Vec-BFS** | 2.0 | 0.5 | Local structure (structural roles) | ⏳ Training |
| **Node2Vec-DFS** | 0.5 | 2.0 | Communities (homophily) | ⏳ Training |

### Modern Methods (2024-2025)

| Method | Description | Status |
|--------|-------------|--------|
| **Graph NE** | Direct structural constraints, no walks | ⏳ Research |
| **Meta Node2Vec** | Heterogeneous graphs (format/archetype) | ⏳ Research |
| **GraphSAGE** | GNN for co-occurrence graphs | ✅ Code ready |

---

## Research Findings

### Node2Vec vs DeepWalk
- **Node2Vec = DeepWalk** when p=q=1
- **Node2Vec-BFS** (p=2, q=0.5): Better for structural roles
- **Node2Vec-DFS** (p=0.5, q=2): Better for communities

### Current State (2024-2025)
- **Node2Vec still competitive** - Despite newer methods
- **Small performance differences** - Walk strategies show slight differences
- **Graph NE emerging** - Simpler, no hyperparameter tuning
- **Meta Node2Vec** - For heterogeneous graphs (we have metadata!)

---

## Implementation

### PEP 723 Scripts

**Compare Methods**:
```bash
uv run --script src/ml/scripts/compare_embedding_methods.py \
  --input data/processed/pairs_large.csv \
  --methods deepwalk node2vec node2vec_bfs node2vec_dfs
```

**Train Single Method**:
```bash
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input data/processed/pairs_large.csv \
  --p 2.0 --q 0.5 --output magic_bfs
```

### PyTorch Geometric Node2Vec

PyG also has Node2Vec:
```python
from torch_geometric.nn import Node2Vec

model = Node2Vec(
    edge_index,
    embedding_dim=128,
    walks_per_node=10,
    walk_length=20,
    p=1.0,
    q=1.0,
)
```

**Advantage**: Can use GPU, integrates with GNNs

---

## Next Steps

### Immediate
1. ✅ Train all Node2Vec variants
2. ⏳ Compare performance on test set
3. ⏳ Tune p, q parameters

### Future
1. **Graph NE** - Simpler alternative
2. **Meta Node2Vec** - Use format/archetype metadata
3. **PyG Node2Vec** - GPU-accelerated, integrate with GNNs

---

## Files

- `src/ml/scripts/compare_embedding_methods.py` - PEP 723 comparison script
- `src/ml/similarity/card_similarity_pecan.py` - PecanPy Node2Vec
- `src/ml/similarity/gnn_embeddings.py` - PyTorch Geometric GNNs
- `GRAPH_EMBEDDING_METHODS.md` - Detailed research summary

---

**Status**: ✅ DeepWalk trained, comparison in progress

