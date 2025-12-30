# GNN Implementation Status

**Date**: 2025-01-27  
**Library**: **PyTorch Geometric** (torch_geometric)

---

## What We're Using

### Library: PyTorch Geometric

**Implementation**: `src/ml/similarity/gnn_embeddings.py`

**Models Supported**:
1. **GraphSAGE** (default, recommended by expert guidance)
2. **GCN** (Graph Convolutional Network)
3. **GAT** (Graph Attention Network)

**Status**: ✅ Code complete, ready for training

---

## Current Implementation

### Architecture
- **Default**: GraphSAGE (best for co-occurrence graphs)
- **Layers**: 2 (shallow, per expert guidance)
- **Hidden Dim**: 128
- **Training**: Link prediction task

### Features
- ✅ Loads graph from edgelist
- ✅ Trains with link prediction
- ✅ Extracts node embeddings
- ✅ Similarity search interface
- ✅ Save/load model and embeddings
- ✅ Integrated into fusion system

---

## Dependencies

**Required**:
- `torch` (PyTorch)
- `torch-geometric` (PyTorch Geometric)

**Status**: Check if installed:
```bash
python3 -c "import torch; import torch_geometric; print('OK')"
```

---

## Training Script

**File**: `src/ml/scripts/train_gnn.py`

**Usage**:
```bash
uv run python -m src.ml.scripts.train_gnn \
  --pairs-csv data/processed/pairs_large.csv \
  --model-type GraphSAGE \
  --hidden-dim 128 \
  --num-layers 2 \
  --epochs 100 \
  --output experiments/signals/gnn_embeddings.json
```

---

## Integration

### Fusion System
- Added `gnn` weight to `FusionWeights`
- Integrated into all aggregation methods
- Can be used alongside other signals

### Rust Integration
- Rust can load pre-trained GNN embeddings (JSON format)
- Used in `SimilarityFunction` for candidate generation

---

## Expert Guidance Applied

Based on `GNN_EXPERT_GUIDANCE.md`:

1. ✅ **GraphSAGE** (best for co-occurrence graphs)
2. ✅ **Shallow** (2 layers)
3. ✅ **Link prediction** training
4. ✅ **Early stopping** and regularization

---

## Next Steps

1. **Install PyTorch Geometric** (if not installed):
   ```bash
   uv add torch torch-geometric
   ```

2. **Train GNN**:
   ```bash
   uv run python -m src.ml.scripts.train_gnn
   ```

3. **Use in fusion**:
   - Load trained embeddings
   - Add to `WeightedLateFusion` with `gnn_embedder` parameter

---

**Status**: ✅ **PyTorch Geometric** - Code ready, needs training

