# Next Steps - Implementation Complete

**Date**: 2025-01-27
**Status**: ✅ All integration complete, ready for data generation and testing

---

## Summary

All multi-signal integration is complete. The API now supports 7 similarity signals with proper loading, caching, and fusion. GNN implementation has been updated based on expert guidance.

---

## ✅ Completed

### 1. GNN Implementation Updated (Expert Guidance) ✅

**Based on Research**:
- ✅ **GraphSAGE** as default (best for co-occurrence graphs)
- ✅ **Shallow architecture** (2 layers, per expert guidance)
- ✅ **Link prediction training** (self-supervised, binary cross-entropy)
- ✅ **Early stopping** and gradient clipping
- ✅ **Proper loss function** (pos/neg edge sampling)

**Files Updated**:
- `src/ml/similarity/gnn_embeddings.py` - Updated training loop
- `src/ml/scripts/train_gnn.py` - **NEW** Training script with expert best practices
- `GNN_EXPERT_GUIDANCE.md` - **NEW** Documentation of expert findings

### 2. Signal Computation Script ✅

**Created**: `src/ml/scripts/compute_and_cache_signals.py`
- Computes sideboard co-occurrence
- Computes temporal (monthly) co-occurrence
- Checks for GNN embeddings
- Saves to `experiments/signals/`

### 3. API Integration ✅

**All signals integrated**:
- Sideboard co-occurrence
- Temporal trends
- Text embeddings
- GNN embeddings

**Files**:
- `src/ml/api/api.py` - Updated state and fusion
- `src/ml/api/load_signals.py` - **NEW** Signal loading module
- `src/ml/similarity/fusion.py` - All similarity methods implemented

---

## 📋 Next Steps (Ready to Execute)

### Step 1: Compute Sideboard & Temporal Signals

```bash
# Compute signals from deck data
uv run python -m src.ml.scripts.compute_and_cache_signals
```

**Expected Output**:
- `experiments/signals/sideboard_cooccurrence.json`
- `experiments/signals/temporal_cooccurrence.json`

**Requirements**:
- `data/processed/decks_with_metadata.jsonl` must exist

### Step 2: Train GNN Model (Optional)

```bash
# Train GraphSAGE model (expert recommended)
uv run python -m src.ml.scripts.train_gnn \
    --pairs-csv data/processed/pairs_large.csv \
    --model-type GraphSAGE \
    --hidden-dim 128 \
    --num-layers 2 \
    --epochs 100 \
    --lr 0.01
```

**Expected Output**:
- `experiments/signals/gnn_graphsage.json`

**Requirements**:
- PyTorch Geometric installed
- `data/processed/pairs_large.csv` must exist

### Step 3: Test API Integration

```bash
# Start API (signals auto-loaded on startup)
export EMBEDDINGS_PATH=data/embeddings/your_embeddings.wv
export PAIRS_PATH=data/processed/pairs_large.csv
export TEXT_EMBEDDER_MODEL=all-MiniLM-L6-v2

uvicorn src.ml.api.api:app --reload
```

**Test Request**:
```bash
curl -X POST http://localhost:8000/v1/similar \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "top_k": 10,
    "mode": "fusion",
    "weights": {
      "embed": 0.20,
      "jaccard": 0.20,
      "functional": 0.15,
      "text_embed": 0.15,
      "sideboard": 0.15,
      "temporal": 0.10,
      "gnn": 0.05
    }
  }'
```

### Step 4: Evaluate Impact

```bash
# Compare performance with/without new signals
# Run evaluation script with different weight configurations
```

---

## 📊 Expert Guidance Applied

### GraphSAGE for Co-Occurrence Graphs

**Why**:
- Best for low-homophily graphs (co-occurrence networks)
- Outperforms GCN on large graphs
- Learnable aggregators adapt to data

**Implementation**:
- Default model type: `GraphSAGE`
- 2 layers (shallow, per expert guidance)
- Link prediction training objective

### Training Best Practices

**Applied**:
- ✅ Self-supervised link prediction
- ✅ Positive/negative edge sampling
- ✅ Binary cross-entropy loss
- ✅ Early stopping (patience=10)
- ✅ Gradient clipping (max_norm=1.0)
- ✅ Weight decay (5e-4)

**Not Yet Applied** (Future Enhancements):
- NeighborLoader for very large graphs
- Node attribute features (color, type, CMC)
- Node2vec initialization

---

## 🔧 Files Created/Modified

### New Files
- `src/ml/scripts/compute_and_cache_signals.py` - Signal computation
- `src/ml/scripts/train_gnn.py` - GNN training script
- `src/ml/api/load_signals.py` - Signal loading module
- `GNN_EXPERT_GUIDANCE.md` - Expert findings documentation
- `INTEGRATION_COMPLETE.md` - Integration summary
- `NEXT_STEPS_COMPLETE.md` - This file

### Modified Files
- `src/ml/similarity/gnn_embeddings.py` - Updated with expert guidance
- `src/ml/api/api.py` - Integrated all signals
- `src/ml/similarity/fusion.py` - Added missing similarity methods
- `src/ml/similarity/sideboard_signal.py` - Fixed import

---

## ⚠️ Known Issues

1. **scipy build failure**: Dependency issue, doesn't block signal computation
2. **GNN training**: Requires PyTorch Geometric (may need separate environment)
3. **Data availability**: Need to verify `decks_with_metadata.jsonl` exists

---

## 🎯 Success Criteria

- [ ] Sideboard signal computed and cached
- [ ] Temporal signal computed and cached
- [ ] GNN model trained (optional)
- [ ] API loads all signals successfully
- [ ] API returns results with all 7 signals
- [ ] Performance evaluation shows improvement

---

## 📚 Documentation

- `INTEGRATION_COMPLETE.md` - Full integration details
- `GNN_EXPERT_GUIDANCE.md` - Expert recommendations
- `LIBRARY_INTEGRATION_IMPROVEMENTS.md` - Rust library improvements
- `STRATEGIC_DATA_PRIORITIES.md` - Original strategic plan

---

## 🚀 Ready to Execute

All code is complete and ready. Next steps are data generation and testing:

1. Run signal computation script
2. (Optional) Train GNN model
3. Test API with all signals
4. Evaluate performance impact
