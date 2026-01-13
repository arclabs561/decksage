# Feature Architecture: How All Signals Work Together

**Date:** January 6, 2026

## Overview

All features are **computed in parallel** and combined using **late fusion** (weighted combination of similarity scores). The GNN does **NOT** consume other features - it's a separate signal.

## Architecture Diagram

```
Query Card: "Lightning Bolt"
         │
         ├─────────────────────────────────────────────────┐
         │                                                 │
         ▼                                                 ▼
    ┌─────────┐                                    ┌─────────────┐
    │  Graph  │                                    │ Card Data   │
    │ (Edges) │                                    │ (Text, URLs)│
    └─────────┘                                    └─────────────┘
         │                                                 │
         │                                                 │
    ┌────┴────┐                                      ┌────┴────┐
    │         │                                      │         │
    ▼         ▼                                      ▼         ▼
┌─────────┐ ┌─────────┐                      ┌──────────┐ ┌──────────┐
│ Co-occ  │ │ Jaccard │                      │   Text   │ │  Visual  │
│ Embed   │ │ Similar │                      │ Embedder │ │ Embedder │
│(Node2Vec│ │         │                      │(E5-base) │ │ (SigLIP) │
│/PecanPy)│ │         │                      └──────────┘ └──────────┘
└─────────┘ └─────────┘                            │         │
    │         │                                    │         │
    └────┬────┘                                    └────┬────┘
         │                                               │
         │         ┌──────────────┐                     │
         └────────▶│   GNN        │◀────────────────────┘
                   │ (GraphSAGE)  │
                   │              │
                   │ Uses ONLY    │
                   │ graph edges  │
                   │ (not other   │
                   │  features)   │
                   └──────────────┘
                         │
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ Co-occ  │    │ Jaccard │    │   GNN   │
    │ Similar │    │ Similar │    │ Similar │
    │  Score  │    │  Score  │    │  Score  │
    └─────────┘    └─────────┘    └─────────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Text   │    │ Visual  │    │Functional│
    │ Similar │    │ Similar │    │  Similar │
    │  Score  │    │  Score  │    │   Score  │
    └─────────┘    └─────────┘    └─────────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  Weighted Late      │
              │  Fusion             │
              │                     │
              │ final_score =       │
              │   w1*coocc +        │
              │   w2*jaccard +      │
              │   w3*gnn +          │
              │   w4*text +         │
              │   w5*visual +       │
              │   w6*functional     │
              └─────────────────────┘
                         │
                         ▼
              Final Ranked Results
```

## Key Points

### 1. **GNN is Separate**
- GNN only uses **graph structure** (co-occurrence edges)
- It does **NOT** consume visual embeddings, text embeddings, or other features
- GNN learns node embeddings from graph topology alone
- Trained using link prediction on the co-occurrence graph

### 2. **All Signals Computed in Parallel**
Each signal is computed independently:
- **Co-occurrence embeddings**: Node2Vec/PecanPy on graph → cosine similarity
- **Jaccard**: Direct set intersection/union on graph neighbors
- **Functional tags**: Jaccard similarity on functional tag sets
- **Text embeddings**: E5-base model on card text → cosine similarity
- **Visual embeddings**: SigLIP on card images → cosine similarity
- **GNN embeddings**: GraphSAGE on graph → cosine similarity

### 3. **Late Fusion Combination**
All similarity scores are combined using weighted sum:
```python
final_score = (
    w_embed * coocc_sim +
    w_jaccard * jaccard_sim +
    w_gnn * gnn_sim +
    w_text * text_sim +
    w_visual * visual_sim +
    w_functional * functional_sim
)
```

### 4. **Default Weights**
```python
FusionWeights(
    embed=0.20,        # Co-occurrence embeddings
    jaccard=0.15,      # Direct co-occurrence
    functional=0.10,   # Functional tags
    text_embed=0.25,   # Text embeddings (E5)
    visual_embed=0.20, # Visual embeddings (SigLIP)
    gnn=0.30,          # GNN embeddings (GraphSAGE)
)
```

## Why This Architecture?

### ✅ Advantages
1. **Modularity**: Each signal can be optimized independently
2. **Flexibility**: Easy to add/remove signals
3. **Interpretability**: Can see contribution of each signal
4. **Efficiency**: Signals computed in parallel, cached separately
5. **Robustness**: If one signal fails, others still work

### ⚠️ Limitations
1. **No cross-modal learning**: Signals don't learn from each other
2. **Weight optimization needed**: Manual tuning or grid search
3. **Scale mismatches**: Different signals have different distributions (addressed with normalization)

## Could We Feed Features Into GNN?

**Technically yes, but not recommended:**

### Option 1: Node Features in GNN
```python
# Could concatenate features as node attributes
node_features = concat([
    text_embedding,      # 384D
    visual_embedding,    # 768D
    functional_tags,      # Sparse
])
# Then GNN would learn to combine graph structure + features
```

**Trade-offs:**
- ✅ Richer representation
- ❌ Requires retraining GNN
- ❌ Less modular (harder to update individual signals)
- ❌ Higher computational cost

### Option 2: Multi-Modal GNN
```python
# Separate GNNs for each modality, then combine
text_gnn = GNN(graph, node_features=text_embeddings)
visual_gnn = GNN(graph, node_features=visual_embeddings)
# Combine outputs
```

**Trade-offs:**
- ✅ More sophisticated
- ❌ Much more complex
- ❌ Harder to debug
- ❌ Requires significant infrastructure changes

## Current Approach is Best

**Late fusion (current approach) is recommended because:**
1. ✅ Research shows it works well for retrieval tasks
2. ✅ Each signal can be optimized independently
3. ✅ Easy to understand and debug
4. ✅ Works with pre-trained models (no retraining needed)
5. ✅ Flexible weight adjustment

**GNN remains separate because:**
- It captures multi-hop relationships in the graph
- It's complementary to other signals (not redundant)
- Keeping it separate allows independent optimization

## Summary

- **GNN**: Uses only graph structure (edges), learns node embeddings
- **Visual embeddings (SigLIP)**: Separate signal, computed from images
- **Text embeddings**: Separate signal, computed from card text
- **All signals**: Combined using weighted late fusion
- **No feature feeding**: GNN doesn't consume other features (by design)

This architecture is **correct and follows best practices** for multimodal similarity search.
