# DeckSage ML Experiment Summary

**Date**: 2025-09-30
**Status**: ✅ **Graph Built Successfully, Python 3.13 Compatibility Issue Found**

---

## What We Accomplished

### 1. End-to-End Data Pipeline ✅

**Extract → Transform → Graph → (Embeddings pending)**

- ✅ **Extracted 198 collections** from MTG datasets (Scryfall + MTGTop8)
- ✅ **Built co-occurrence graph**: 8,207 unique cards, 186,608 card pairs
- ✅ **Exported to CSV**: 7.8MB `pairs.csv` ready for ML

### 2. Graph Statistics

```
Collections processed: 198
Total unique cards: 8,207
Total edges created: 241,583
Unique card pairs: 186,608
Compression ratio: 1.3x
```

### 3. Implementation Choices

**Reviewed 3 Node2Vec Implementations:**

1. **PyTorch Geometric** - Full GNN framework, heavy dependencies
2. **[fastnode2vec](https://github.com/louisabraham/fastnode2vec)** - Fast, 96 stars, linear memory
3. **[PecanPy](https://github.com/krishnanlab/PecanPy)** ⭐ **BEST** - 169 stars, peer-reviewed (Bioinformatics 2021), 3 optimized modes

**Selected: PecanPy**
- Published research (Liu & Krishnan, 2021)
- Optimized for different graph types (PreComp, SparseOTF, DenseOTF)
- node2vec+ for weighted graphs (perfect for co-occurrence data)
- Active maintenance (342 commits)

### 4. Technical Blocker Found

**Python 3.13 Incompatibility**: gensim (required by PecanPy) has C extension compilation errors with Python 3.13

**Solution Options**:
1. Use Python 3.11 or 3.12 (recommended)
2. Wait for gensim update for Python 3.13
3. Use alternative embeddings (networkx + sklearn)

---

## Code Created

### Graph Export Tool

**File**: `src/backend/cmd/quick-graph/main.go`
- Fast, direct graph builder
- Processes 198 collections in ~1 minute
- Detailed progress logging
- Outputs standard CSV format

### ML Experiment Scripts

1. **`src/ml/card_similarity_pecan.py`** - PecanPy implementation
   - Complete CLI interface
   - t-SNE visualization
   - Similarity search
   - Model persistence

2. **`src/ml/requirements_fast.txt`** - Dependencies

### Graph Data

**File**: `src/backend/pairs.csv` (7.8MB)
```csv
NAME_1,NAME_2,COUNT_SET,COUNT_MULTISET
Lightning Bolt,Monastery Swiftspear,42,336
Lightning Bolt,Lava Spike,38,608
...
```

---

## Next Steps

### Immediate (To Complete Experiment)

```bash
# Option 1: Use Python 3.12
cd src/ml
uv venv --python 3.12
source .venv/bin/activate
uv pip install pecanpy pandas matplotlib scikit-learn

# Run experiment
python card_similarity_pecan.py \\
  --input ../backend/pairs.csv \\
  --dim 128 \\
  --walk-length 80 \\
  --num-walks 10 \\
  --epochs 10 \\
  --visualize \\
  --query "Lightning Bolt" "Brainstorm" "Sol Ring"
```

### Expected Output

1. **Embeddings**: `magic_pecanpy.wv` (gensim format)
2. **Visualization**: `magic_pecanpy_tsne.png` (t-SNE plot)
3. **Similarity Results**: Top 10 similar cards for each query

### Medium-term (Integration)

1. Add REST API endpoint for similarity search
2. Build recommendation UI
3. Cross-game similarity (after adding Yu-Gi-Oh!)
4. Deploy to production

---

## Architecture Validation

### Data Flow Proven

```
MTG Decks → Go Extract → Transform → CSV Graph → Python ML → Embeddings
    ✅           ✅            ✅         ✅          ⏸️           ⏸️
```

**Working**:
- Multi-game architecture
- Graph building pipeline
- Fast data export
- ML scripts ready

**Pending**:
- Python 3.12/3.11 environment
- Embedding training
- Similarity API

---

## Performance Notes

### Graph Building

- **Speed**: 198 collections in ~60 seconds
- **Memory**: O(unique pairs) = ~20MB in memory
- **Output**: 7.8MB compressed to CSV
- **Scalability**: Linear with collections

### Expected ML Performance

Based on PecanPy benchmarks:
- **8K nodes, 186K edges**: ~2-5 minutes training
- **Memory**: <1GB RAM
- **Output**: ~4MB embeddings file

---

## Key Learnings

1. **Go + Python Integration**: Go for data processing, Python for ML works well
2. **Graph Compression**: 241K edges → 186K unique pairs (1.3x compression)
3. **Tool Selection**: Peer-reviewed > stars (PecanPy over fastnode2vec)
4. **Python Compatibility**: Check Python version compatibility early

---

## Files Created

### Backend (Go)
- `cmd/quick-graph/main.go` - Fast graph export
- `cmd/export-graph/main.go` - Transform-based export (unused)
- `pairs.csv` - Co-occurrence graph data

### ML (Python)
- `card_similarity_pecan.py` - PecanPy experiment
- `card_embeddings.py` - PyTorch Geometric (archived)
- `card_embeddings_fast.py` - fastnode2vec (archived)
- `requirements_fast.txt` - Dependencies

### Documentation
- `ML_EXPERIMENT_SUMMARY.md` - This file
- `SESSION_ARCHITECTURE_REFACTOR.md` - Architecture changes
- `ADDING_A_NEW_GAME.md` - Multi-game guide

---

## Citations

**PecanPy**:
Liu R, Krishnan A (2021) PecanPy: a fast, efficient, and parallelized Python implementation of node2vec. _Bioinformatics_
https://doi.org/10.1093/bioinformatics/btab202

**Node2Vec+**:
Liu R, Hirn M, Krishnan A (2023) Accurately modeling biased random walks on weighted graphs using node2vec+. _Bioinformatics_
https://doi.org/10.1093/bioinformatics/btad047

---

## Status Summary

✅ **Data pipeline**: Complete
✅ **Graph export**: Complete (198 collections → 186K pairs)
✅ **ML scripts**: Ready
⚠️ **Environment**: Need Python 3.11/3.12
⏸️ **Embeddings**: Blocked on Python version
⏸️ **API**: Pending embeddings

**To unblock**: Install Python 3.12 or wait for gensim Python 3.13 compatibility

**Total Progress**: ~80% complete (pipeline works, just need compatible Python)
