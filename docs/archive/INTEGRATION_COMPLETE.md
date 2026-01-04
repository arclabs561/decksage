# Multi-Signal Integration Complete

**Date**: 2025-01-27
**Status**: ✅ All signals integrated into API

---

## Summary

Successfully integrated sideboard, temporal, text embeddings, and GNN signals into the FastAPI similarity service. The API now supports multi-modal similarity with 7 signals:

1. **Embedding** (Node2Vec/PecanPy)
2. **Jaccard** (Co-occurrence graph)
3. **Functional Tags** (Rule-based classification)
4. **Text Embeddings** (Card Oracle text semantic similarity) ✨ NEW
5. **Sideboard** (Sideboard co-occurrence patterns) ✨ NEW
6. **Temporal** (Time-based co-occurrence trends) ✨ NEW
7. **GNN** (Graph Neural Network embeddings) ✨ NEW

---

## Changes Made

### 1. API State (`src/ml/api/api.py`)

**Added fields to `ApiState`**:
```python
self.sideboard_cooccurrence: dict[str, dict[str, float]] | None = None
self.temporal_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None
self.text_embedder: object | None = None
self.gnn_embedder: object | None = None
```

### 2. Fusion Integration (`src/ml/api/api.py`)

**Updated `_similar_fusion`** to pass all signals to `WeightedLateFusion`:
```python
fusion = WeightedLateFusion(
    state.embeddings,
    state.graph_data["adj"],
    tagger,
    fw,
    aggregator=(request.aggregator or "weighted"),
    rrf_k=int(request.rrf_k or 60),
    mmr_lambda=float(request.mmr_lambda or 0.0),
    text_embedder=state.text_embedder,
    card_data=state.card_attrs,
    sideboard_cooccurrence=state.sideboard_cooccurrence,
    temporal_cooccurrence=state.temporal_cooccurrence,
    gnn_embedder=state.gnn_embedder,
)
```

**Updated `SimilarityRequest`** to accept new weight parameters:
- `text_embed`, `sideboard`, `temporal`, `gnn` weights can now be specified

### 3. Signal Loading (`src/ml/api/load_signals.py`)

**New module** for loading pre-computed signals:
- Loads sideboard co-occurrence from JSON
- Loads temporal (monthly) co-occurrence from JSON
- Loads GNN embeddings from JSON
- Initializes text embedder (lazy loading)

**Auto-loaded on API startup** via `lifespan` handler.

### 4. Signal Computation Script (`src/ml/scripts/compute_and_cache_signals.py`)

**New script** to pre-compute and cache signals:
```bash
python -m src.ml.scripts.compute_and_cache_signals
```

Computes:
- Sideboard co-occurrence → `experiments/signals/sideboard_cooccurrence.json`
- Temporal co-occurrence → `experiments/signals/temporal_cooccurrence.json`
- GNN embeddings (if available) → `experiments/signals/gnn_embeddings.json`

### 5. Bug Fixes

- Fixed missing `json` import in `src/ml/similarity/sideboard_signal.py`

---

## Usage

### 1. Compute Signals

```bash
# Compute and cache sideboard/temporal signals
python -m src.ml.scripts.compute_and_cache_signals
```

### 2. Start API with Signals

```bash
# Set environment variables
export EMBEDDINGS_PATH=path/to/embeddings.wv
export PAIRS_PATH=path/to/pairs.csv
export TEXT_EMBEDDER_MODEL=all-MiniLM-L6-v2  # Optional

# Start API (signals auto-loaded)
uvicorn src.ml.api.api:app --reload
```

### 3. Use New Signals in API

```python
# Example request with custom weights
{
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
}
```

---

## Default Weights

If no weights specified, uses:
- `embed`: 0.20
- `jaccard`: 0.20
- `functional`: 0.15
- `text_embed`: 0.15
- `sideboard`: 0.15
- `temporal`: 0.10
- `gnn`: 0.05

(Weights are normalized to sum to 1.0)

---

## Next Steps

1. **Run Signal Computation**: Generate sideboard/temporal signals from deck data
2. **Train GNN Model**: Generate GNN embeddings (separate training script)
3. **Evaluate Impact**: Compare P@10 with/without new signals
4. **Tune Weights**: Use grid search to find optimal weight combination

---

## Files Modified

- `src/ml/api/api.py` - API state, fusion integration, request model
- `src/ml/similarity/sideboard_signal.py` - Fixed missing import
- `src/ml/api/load_signals.py` - **NEW** Signal loading module
- `src/ml/scripts/compute_and_cache_signals.py` - **NEW** Signal computation script

---

## Related Files

- `src/ml/similarity/fusion.py` - Already supports all signals
- `src/ml/similarity/sideboard_signal.py` - Sideboard computation
- `src/ml/analysis/temporal_trends.py` - Temporal computation
- `src/ml/similarity/text_embeddings.py` - Text embedding model
- `src/ml/similarity/gnn_embeddings.py` - GNN embedding model

---

## Testing

To test the integration:

```bash
# 1. Compute signals
python -m src.ml.scripts.compute_and_cache_signals

# 2. Start API
uvicorn src.ml.api.api:app --reload

# 3. Test with curl
curl -X POST http://localhost:8000/v1/similar \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lightning Bolt",
    "top_k": 10,
    "mode": "fusion",
    "weights": {
      "sideboard": 0.3,
      "temporal": 0.2
    }
  }'
```

---

## Status

✅ **API Integration**: Complete
✅ **Signal Loading**: Complete
✅ **Signal Computation**: Script ready
🟡 **GNN Training**: Separate task (placeholder ready)
🟡 **Evaluation**: Pending (run after signals computed)
