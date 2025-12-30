# GNN Expert Guidance - What Actually Works

**Date**: 2025-01-27  
**Based on**: Expert research and best practices for graph embedding and similarity tasks

---

## Key Findings

### 1. **GraphSAGE is Best for Co-Occurrence Graphs** ⭐⭐⭐⭐⭐

**Why**:
- Excels on **low-homophily graphs** (common in co-occurrence networks)
- Significantly outperforms GCN on large graphs
- Uses learnable aggregators that adapt to data structure
- Benefits from deeper stacks (unlike GCN/GAT)

**Recommendation**: Use `SAGEConv` with `NeighborLoader` for scalable sampling

### 2. **Keep Models Shallow** ⚠️

**Finding**: Adding more layers to GCN or GraphSAGE did NOT yield performance gains

**Recommendation**: 
- Use **2 layers** (not deeper)
- Focus on better features/attributes rather than depth

### 3. **Node2vec Remains Strong Baseline** ✅

**Finding**: Node2vec is still competitive in 2024, especially for:
- Community detection on sparse networks
- Degree-agnostic embeddings
- Capturing indirect relationships

**Recommendation**: Keep Node2vec as baseline, use GNNs to potentially exceed it

### 4. **Training Best Practices**

**Self-Supervised Link Prediction**:
- Predict edge existence/weights
- Sample positive edges (existing)
- Sample negative edges (non-existent)
- Binary cross-entropy or MSE loss

**Memory Management**:
- Use `NeighborLoader` for large graphs
- Sample neighborhoods rather than full graph
- Consider full-graph training only if memory allows

**Hyperparameters**:
- Learning rate: 0.01-0.005
- Hidden dim: 128-256
- Dropout: 0.5-0.6
- Epochs: 50-100 (early stopping recommended)

### 5. **Use Edge Attributes** ✅

**Finding**: Edge attributes (co-occurrence counts, weights) improve performance

**Recommendation**: 
- Use edge weights in attention/aggregation
- Consider edge type information if available

---

## Updated Implementation Strategy

### Model Choice: **GraphSAGE** (not GCN/GAT)

```python
from torch_geometric.nn import SAGEConv
from torch_geometric.loader import NeighborLoader

# 2 layers (shallow)
model = GraphSAGE(
    in_channels=feature_dim,
    hidden_channels=128,
    out_channels=64,
    num_layers=2  # Keep shallow!
)
```

### Training Objective: **Link Prediction**

```python
# Self-supervised: predict edge weights
pos_edges = sample_positive_edges(edge_index, edge_attr)
neg_edges = sample_negative_edges(num_nodes)

# Predict similarity
pos_scores = (embeddings[pos_src] * embeddings[pos_dst]).sum(dim=1)
neg_scores = (embeddings[neg_src] * embeddings[neg_dst]).sum(dim=1)

# Binary cross-entropy loss
loss = pos_loss + neg_loss
```

### Node Features: **Use Attributes**

Instead of one-hot identity matrix:
- Card attributes (color, type, CMC)
- Degree centrality
- Node2vec embeddings (as initialization)

---

## Comparison with Current Implementation

### Current Issues:
1. ❌ Uses GCN by default (should be GraphSAGE)
2. ❌ Uses one-hot identity features (should use attributes)
3. ❌ Simple MSE loss on edge weights (should use link prediction)
4. ❌ No neighbor sampling (should use NeighborLoader for large graphs)

### Recommended Changes:
1. ✅ Switch default to GraphSAGE
2. ✅ Add node attribute features
3. ✅ Implement proper link prediction training
4. ✅ Add NeighborLoader for scalability

---

## Sources

1. Expert analysis: GraphSAGE vs GCN vs GAT for co-occurrence graphs
2. Best practices: GNN training for node similarity and embedding
3. PyTorch Geometric documentation and examples

