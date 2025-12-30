# Graph Embedding Methods: Current State (2024-2025)

**Date**: 2025-01-27  
**Status**: Research complete, implementation ready

---

## Classical Methods (Still Competitive)

### 1. DeepWalk (2014)
- **What**: Random walks + Word2Vec
- **Parameters**: p=1, q=1 (unbiased)
- **Status**: ✅ Simple baseline, still used
- **When to use**: Quick baseline, small graphs

### 2. Node2Vec (2016)
- **What**: DeepWalk with controllable p, q parameters
- **Parameters**:
  - **p** (return): Controls backtracking (high p = stay local)
  - **q** (in-out): Controls exploration (high q = BFS, low q = DFS)
- **Status**: ✅ Still competitive, widely used
- **When to use**: Need to balance local structure (BFS) vs communities (DFS)

**Variants**:
- **Node2Vec-BFS** (p=2, q=0.5): Explores local structure, structural roles
- **Node2Vec-DFS** (p=0.5, q=2): Explores communities, homophily
- **Node2Vec-Default** (p=1, q=1): Equivalent to DeepWalk

---

## Modern Methods (2024-2025)

### 3. Graph NE (Neighbor Embeddings)
- **What**: Direct structural constraints, no random walks
- **Advantages**:
  - Simpler than Node2Vec
  - No hyperparameter tuning (p, q)
  - Outperforms Node2Vec in some tasks
  - Better local structure preservation
- **Status**: ⭐ Emerging, promising
- **Implementation**: Not yet in our codebase

### 4. Meta Node2Vec / Metapath2Vec
- **What**: For heterogeneous graphs (multiple node/edge types)
- **Use case**: We have format, archetype, card type metadata
- **Status**: ⚠️ Not yet implemented, could leverage our metadata
- **When to use**: When you have node/edge attributes (format, archetype)

---

## Current Implementation

### What We're Using: PecanPy (Node2Vec)

**File**: `src/ml/similarity/card_similarity_pecan.py`

**Features**:
- ✅ Fast, parallelized Node2Vec
- ✅ Supports weighted graphs (node2vec+)
- ✅ Multiple modes (PreComp, SparseOTF, DenseOTF)
- ✅ Configurable p, q parameters

**Current Settings**:
- p=1, q=1 (DeepWalk equivalent)
- dim=128
- walk_length=80
- num_walks=10
- window=10

---

## Research Findings (2024-2025)

### Performance Comparison
1. **Node2Vec still competitive** - Despite newer methods, Node2Vec remains strong
2. **Small performance differences** - Different walk strategies show only slight differences in link prediction
3. **Graph NE emerging** - Simpler, no hyperparameter tuning, better in some tasks
4. **TSAW (True Self-Avoiding Walk)** - Reaches unknown nodes faster

### Key Insights
- **Random walks are resilient** - Network structure recovered regardless of walk heuristic
- **Hyperparameter tuning matters** - p, q can significantly affect results
- **Local vs global tradeoff** - BFS (local structure) vs DFS (communities)

---

## Recommendations for Our Use Case

### Current: Node2Vec (PecanPy)
✅ **Keep using** - Still competitive, well-tested

### Improvements:
1. **Tune p, q** - Try BFS (p=2, q=0.5) and DFS (p=0.5, q=2) variants
2. **Add Graph NE** - Simpler alternative, no hyperparameter tuning
3. **Meta Node2Vec** - Leverage format/archetype metadata for heterogeneous graphs
4. **Ensemble** - Combine multiple methods (DeepWalk + Node2Vec variants)

---

## Implementation Plan

### Phase 1: Compare Variants (Now)
- ✅ DeepWalk (p=1, q=1)
- ✅ Node2Vec-Default (p=1, q=1)
- ✅ Node2Vec-BFS (p=2, q=0.5)
- ✅ Node2Vec-DFS (p=0.5, q=2)

**Script**: `src/ml/scripts/compare_embedding_methods.py` (PEP 723)

### Phase 2: Add Graph NE
- Research Graph NE implementation
- Compare to Node2Vec baseline

### Phase 3: Meta Node2Vec
- Use format/archetype metadata
- Heterogeneous graph embeddings

---

## Usage

### Compare Methods (PEP 723)
```bash
uv run --script src/ml/scripts/compare_embedding_methods.py \
  --input data/processed/pairs_large.csv \
  --methods deepwalk node2vec node2vec_bfs node2vec_dfs \
  --dim 128
```

### Train Single Method
```bash
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input data/processed/pairs_large.csv \
  --p 2.0 --q 0.5 \
  --output magic_bfs
```

---

**Status**: ✅ Node2Vec (PecanPy) - Current, competitive  
**Next**: Compare variants, add Graph NE, explore Meta Node2Vec

