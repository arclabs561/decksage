# LLM Judgments in the Training/Evaluation Pipeline

## Overview

LLM judgments serve as **ground truth labels** for evaluation and optimization, but **NOT** for training. The training is unsupervised (graph structure only).

---

## Complete Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. TEST SET CREATION (LLM Labels → Ground Truth)               │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ LLM generates labels
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ test_set_labeled_magic.json          │
        │ {                                    │
        │   "Lightning Bolt": {                │
        │     "highly_relevant": ["Shock", ...]│
        │     "relevant": ["Bolt of Keranos"] │
        │     ...                              │
        │   }                                  │
        │ }                                    │
        └─────────────────────────────────────┘
                          │
                          │ Used as ground truth
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
        ▼                                   ▼
┌──────────────────┐              ┌──────────────────┐
│ 2. HYPERPARAMETER│              │ 4. EVALUATION     │
│    SEARCH        │              │                  │
└──────────────────┘              └──────────────────┘
        │                                   │
        │ For each config:                 │ Load embeddings
        │   ├─ Train embedding             │ For each query:
        │   ├─ Evaluate on test set        │   ├─ Get top-k
        │   ├─ Compute P@10, MRR           │   ├─ Check vs labels
        │   └─ Track best                  │   └─ Compute metrics
        │                                   │
        ▼                                   ▼
┌──────────────────┐              ┌──────────────────┐
│ Best Config      │              │ Performance      │
│ {p, q, dim, ...} │              │ {P@10, MRR, ...} │
└──────────────────┘              └──────────────────┘
        │                                   │
        │                                   │
        ▼                                   ▼
┌─────────────────────────────────────────────────────┐
│ 3. TRAINING (Unsupervised - NO LLM Labels)         │
└─────────────────────────────────────────────────────┘
                          │
                          │ Input: Graph structure only
                          │ (co-occurrence pairs)
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ Train Node2Vec/PecanPy               │
        │ - Random walks on graph              │
        │ - Skip-gram objective                │
        │ - NO labels used                    │
        └─────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ embeddings.wv                        │
        │ (Vector representations)             │
        └─────────────────────────────────────┘
                          │
                          │ Used in:
                          │ - Evaluation (step 4)
                          │ - Fusion (step 5)
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│ 5. FUSION WEIGHT OPTIMIZATION                       │
└─────────────────────────────────────────────────────┘
                          │
                          │ Measure individual signals:
                          │ - Embedding: P@10 = X
                          │ - Jaccard: P@10 = Y
                          │ - Functional: P@10 = Z
                          │
                          │ Grid search weights
                          │ Evaluate fusion on test set
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ Best Fusion Weights                 │
        │ {embed: 0.63, jaccard: 0.37, ...}   │
        └─────────────────────────────────────┘
```

---

## Key Points

### 1. **LLM Labels = Ground Truth (Not Training Data)**

- LLM generates labels for test queries
- These labels define what "correct" predictions are
- Format: `{query: {highly_relevant: [...], relevant: [...], ...}}`
- Used for **evaluation only**, not training

### 2. **Training is Unsupervised**

- Embeddings are trained on **graph structure** (co-occurrence pairs)
- No labels used during training
- Node2Vec/PecanPy learns from random walks
- Training objective: predict context nodes from center node

### 3. **Evaluation Uses LLM Labels**

Every evaluation step compares model predictions against LLM labels:

```python
# From improve_embeddings_hyperparameter_search.py
def evaluate_embedding(wv, test_set, ...):
    for query, labels in test_set.items():  # labels = LLM-generated
        predictions = wv.most_similar(query, topn=10)
        
        # Check predictions against LLM labels
        hits = sum(1 for pred in predictions 
                   if pred in labels["highly_relevant"] or 
                      pred in labels["relevant"] or ...)
        
        p_at_k = hits / 10
```

### 4. **Hyperparameter Search = Evaluation Loop**

```python
# From improve_embeddings_hyperparameter_search.py
for p, q, dim, ... in grid_search_space:
    # Train (no labels)
    wv = train_embedding(edgelist_file, p=p, q=q, ...)
    
    # Evaluate (uses LLM labels)
    metrics = evaluate_embedding(wv, test_set, ...)  # test_set has LLM labels
    
    # Track best
    if metrics["p@10"] > best_p@10:
        best_config = {p, q, dim, ...}
```

### 5. **Fusion Optimization = Evaluation Loop**

```python
# From optimize_fusion_weights.py
for embed_w, jaccard_w, func_w in weight_grid:
    fusion = WeightedLateFusion(weights={embed: embed_w, ...})
    
    # Evaluate fusion on test set (uses LLM labels)
    metrics = evaluate_similarity(test_set, fusion.similar, ...)
    
    # Track best
    if metrics["p@10"] > best_p@10:
        best_weights = {embed: embed_w, ...}
```

---

## Where LLM Judgments Are Used

| Stage | Uses LLM Labels? | Purpose |
|-------|------------------|---------|
| **Test Set Creation** | ✅ Yes (generates them) | Create ground truth |
| **Training** | ❌ No | Unsupervised learning |
| **Hyperparameter Search** | ✅ Yes (evaluation) | Select best config |
| **Evaluation** | ✅ Yes (ground truth) | Measure performance |
| **Fusion Optimization** | ✅ Yes (evaluation) | Select best weights |
| **Model Comparison** | ✅ Yes (evaluation) | Compare methods |

---

## Alternative: LLM-as-Judge (Runtime Evaluation)

Instead of pre-generating labels, you can use LLM to judge predictions at runtime:

```python
# From llm_judge_batch.py
def judge_predictions(test_set, predictions, ...):
    for query, preds in predictions.items():
        for candidate, score in preds:
            # LLM judges each prediction
            judgment = llm_judge_similarity(query, candidate)
            # Returns: relevance (0-4), reasoning, confidence
```

**Use cases:**
- When test set is incomplete
- For generating new test set labels
- For large-scale evaluation (cheaper than human annotation)

---

## Summary

**LLM judgments are the evaluation backbone:**

1. **Create** test set labels (ground truth)
2. **Evaluate** embeddings after training
3. **Optimize** hyperparameters (select best config)
4. **Optimize** fusion weights (select best combination)
5. **Compare** different methods/models

**They are NOT used for training** - embeddings learn from graph structure alone.

---

## Current Status

- ✅ Test set: 100 queries (target reached)
- ✅ Labels: 100/100 queries labeled (LLM + fallback)
- ⏳ Hyperparameter search: Running (uses test set for evaluation)
- ⏳ Fusion optimization: Pending (will use test set after embeddings improve)

