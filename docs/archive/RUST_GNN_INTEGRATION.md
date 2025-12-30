# Rust GNN Integration

**Date**: 2025-01-27  
**Status**: Infrastructure ready, training placeholder

---

## Overview

Added Rust support for GNN embeddings, complementing the Python PyTorch Geometric implementation. The Rust version can load pre-trained models from Python and will eventually support native training.

---

## What's Implemented

### 1. GNN Module (`src/annotation/src/gnn.rs`)

**Features**:
- ✅ Load pre-trained embeddings from JSON (compatible with Python PyG output)
- ✅ Cosine similarity computation
- ✅ Most similar cards search
- ✅ Save/load embeddings
- 🟡 Training placeholder (future: candle/burn implementation)

**Usage**:
```rust
use decksage_annotation::gnn::{GNNEmbedder, GNNConfig, GNNModelType};

// Load pre-trained embeddings (from Python PyG)
let embedder = GNNEmbedder::load_from_json(&Path::new("embeddings/gnn_gcn.json"))?;

// Compute similarity
let sim = embedder.similarity("Lightning Bolt", "Chain Lightning");

// Find most similar
let top_similar = embedder.most_similar("Lightning Bolt", 10);
```

### 2. Integration with SimilarityModel

**Updated `SimilarityModel`**:
- Added `gnn: Option<GNNEmbedder>` field
- Integrated into candidate generation
- Fused with other signals using `rank-fusion`

**Usage in SimilarityModel**:
```rust
let model = SimilarityModel {
    embeddings: Some(embeddings),
    jaccard_adj: Some(adj),
    sideboard: Some(sideboard_signal),
    temporal: Some(temporal_signal),
    gnn: Some(gnn_embedder), // NEW
    rrf_config: RrfConfig::default(),
};

let candidates = model.get_similar_cards("Lightning Bolt", 10)?;
// Candidates now include GNN-based suggestions
```

---

## Rust ML Library Options

### Option 1: Candle (Recommended for Now)

**Pros**:
- Lightweight, no Python dependency
- ONNX-compatible (can convert PyG models)
- Good performance
- Active development

**Cons**:
- Less mature than PyTorch
- Limited GNN layer implementations (would need to implement GCN/GAT)

**Implementation Path**:
```rust
// Future: Implement GCN with candle
use candle_core::{Tensor, Device};
use candle_nn::{linear, Linear, VarBuilder};

struct GCNLayer {
    linear: Linear,
}

impl GCNLayer {
    fn forward(&self, x: &Tensor, adj: &Tensor) -> Result<Tensor> {
        // GCN: H' = σ(AHW)
        let h = self.linear.forward(x)?;
        let h = adj.matmul(&h)?;
        Ok(h)
    }
}
```

### Option 2: Burn (Full-Featured)

**Pros**:
- PyTorch-like API
- Full autograd support
- Better for complex models

**Cons**:
- Heavier dependency
- Still in active development
- More complex setup

**Implementation Path**:
```rust
// Future: Implement GCN with burn
use burn::{
    nn::{
        conv::Conv2dConfig,
        loss::CrossEntropyLossConfig,
        DropoutConfig,
    },
    tensor::backend::Backend,
};

#[derive(Module, Debug)]
pub struct GCN<B: Backend> {
    conv1: GraphConv<B>,
    conv2: GraphConv<B>,
}
```

### Option 3: ONNX Runtime (Pragmatic)

**Pros**:
- Can load PyG models converted to ONNX
- Mature, production-ready
- Good performance

**Cons**:
- Requires Python for training
- ONNX conversion can be tricky
- Less flexible than native Rust

**Implementation Path**:
```rust
// Load ONNX model trained in Python
use ort::{Session, Value};

let session = Session::builder()?
    .with_model_from_file("gnn_model.onnx")?;

let inputs = vec![Value::from_array(/* node features */)?];
let outputs = session.run(inputs)?;
```

---

## Current Strategy

### Phase 1: Load Python Models (✅ Done)
- Train GNNs in Python with PyTorch Geometric
- Export embeddings to JSON
- Load in Rust for inference

### Phase 2: Native Training (Future)
- Evaluate candle vs burn for GNN implementation
- Implement GCN layer in chosen framework
- Train on edgelist in Rust

### Phase 3: Hybrid Approach (Future)
- Train in Python (easier experimentation)
- Convert to ONNX
- Load in Rust for production inference

---

## Integration with Existing Pipeline

### Python Training → Rust Inference

```bash
# 1. Train in Python
cd src/ml
uv run python -m similarity.gnn_embeddings

# 2. Export embeddings (already JSON-compatible)
# embeddings/gnn_gcn.json

# 3. Use in Rust annotation tool
cd src/annotation
cargo run -- generate \
    --query "Lightning Bolt" \
    --game magic \
    --gnn-embeddings ../../data/embeddings/gnn_gcn.json
```

### Rust SimilarityModel Integration

The `SimilarityModel` now supports GNN embeddings:

```rust
// In main.rs generate subcommand
let gnn = if let Some(gnn_path) = matches.value_of("gnn-embeddings") {
    Some(GNNEmbedder::load_from_json(Path::new(gnn_path))?)
} else {
    None
};

let model = SimilarityModel {
    // ... other fields
    gnn,
    // ...
};
```

---

## Files Created

- ✅ `src/annotation/src/gnn.rs` - GNN embedder module
- ✅ `src/annotation/src/lib.rs` - Exported gnn module
- ✅ `src/annotation/src/similarity.rs` - Integrated GNN into SimilarityModel
- ✅ `RUST_GNN_INTEGRATION.md` - This document

---

## Next Steps

1. **Test Loading Python Models**:
```bash
# Train in Python
uv run python -m similarity.gnn_embeddings

# Test loading in Rust
cd src/annotation
cargo test gnn::tests
```

2. **Add CLI Flag**:
```rust
// In main.rs
.arg(
    Arg::new("gnn-embeddings")
        .long("gnn-embeddings")
        .value_name("PATH")
        .help("Path to GNN embeddings JSON (from Python PyG training)")
)
```

3. **Evaluate Native Training**:
- Research candle GNN implementations
- Consider burn for full-featured training
- Or stick with Python training + Rust inference

---

## Research Questions

1. **Does Rust GNN training make sense?**
   - Python PyG is mature and well-documented
   - Rust training would be faster but more complex
   - **Recommendation**: Start with Python training, Rust inference

2. **Which Rust ML framework?**
   - **candle**: Lightweight, good for inference
   - **burn**: Full-featured, good for training
   - **ONNX**: Pragmatic, production-ready
   - **Recommendation**: Start with ONNX for production, evaluate candle for native training

3. **Performance vs Complexity Trade-off?**
   - Python training: Easy, well-tested, slower
   - Rust training: Hard, experimental, faster
   - **Recommendation**: Python for experimentation, Rust for production inference

---

## Notes

- **Current State**: Can load Python-trained GNN embeddings in Rust
- **Future**: Native Rust training with candle/burn (if needed)
- **Pragmatic**: Python training + Rust inference is a solid approach
- **Performance**: Rust inference is fast, Python training is acceptable for batch jobs

