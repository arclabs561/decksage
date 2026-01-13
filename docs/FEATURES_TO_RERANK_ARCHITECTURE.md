# Features → Rerank Architecture: Proper Learning-to-Rank Pipeline

**Date:** January 6, 2026
**Status:** Architecture Design - Implementation Needed

## Core Insight

This is a **learning-to-rank problem** with two distinct phases:

1. **Feature Extraction**: Compute similarity scores from each modality
2. **Reranking**: Use a learned model to optimally combine features

Currently, we're doing **manual fusion** instead of **learned reranking**.

## Current vs. Target Architecture

### Current (Manual Fusion) ❌

```
Query → Extract Scores → Manual Fusion (weighted/RRF) → Results
         [embed, jaccard, text, visual, gnn]    [fixed weights]
```

**Problems:**
- No learning from data
- Fixed weights for all queries
- No feature interactions
- Linear combination only

### Target (Learned Reranking) ✅

```
Query → Extract Features → Learned Reranker → Results
         [scores, ranks,    [LightGBM/XGBoost]
          aggregation,      [learns optimal
          query context,     combination]
          agreement]
```

**Advantages:**
- Learns optimal combination from labeled data
- Can learn non-linear relationships
- Can adapt to query context
- Can learn feature interactions

## Feature Extraction Phase

### Current Feature Extraction (Incomplete)

```python
# Only extracts similarity scores
features = {
    "embed_score": 0.85,
    "jaccard_score": 0.72,
    "text_embed_score": 0.91,
    "visual_embed_score": 0.68,
    "gnn_score": 0.79,
}
```

### Comprehensive Feature Extraction (Needed)

```python
def extract_all_features(
    query: str,
    candidate: str,
    fusion: WeightedLateFusion
) -> dict[str, float]:
    """Extract comprehensive feature set for LTR."""

    # Get all similarity scores
    scores = fusion._compute_similarity_scores(query, {candidate})
    candidate_scores = scores.get(candidate, {})

    # Get rank positions (need to compute)
    ranks = _get_rank_positions(query, candidate, fusion)

    # Get query and candidate metadata
    query_meta = _get_card_metadata(query)
    candidate_meta = _get_card_metadata(candidate)

    features = {
        # === Direct Similarity Scores ===
        "embed_score": candidate_scores.get("embed", 0.0),
        "jaccard_score": candidate_scores.get("jaccard", 0.0),
        "functional_score": candidate_scores.get("functional", 0.0),
        "text_embed_score": candidate_scores.get("text_embed", 0.0),
        "visual_embed_score": candidate_scores.get("visual_embed", 0.0),
        "gnn_score": candidate_scores.get("gnn", 0.0),
        "sideboard_score": candidate_scores.get("sideboard", 0.0),
        "temporal_score": candidate_scores.get("temporal", 0.0),
        "archetype_score": candidate_scores.get("archetype", 0.0),
        "format_score": candidate_scores.get("format", 0.0),

        # === Rank Positions (for RRF-style methods) ===
        "embed_rank": ranks.get("embed", 999),
        "jaccard_rank": ranks.get("jaccard", 999),
        "text_embed_rank": ranks.get("text_embed", 999),
        "visual_embed_rank": ranks.get("visual_embed", 999),
        "gnn_rank": ranks.get("gnn", 999),

        # === Aggregation Features ===
        "num_modalities": sum(1 for v in candidate_scores.values() if v > 0),
        "max_score": max(candidate_scores.values()) if candidate_scores else 0.0,
        "min_score": min(candidate_scores.values()) if candidate_scores else 0.0,
        "mean_score": np.mean(list(candidate_scores.values())) if candidate_scores else 0.0,
        "score_variance": np.var(list(candidate_scores.values())) if candidate_scores else 0.0,
        "score_range": (max(candidate_scores.values()) - min(candidate_scores.values()))
                      if candidate_scores else 0.0,

        # === Cross-Modal Agreement ===
        "text_visual_agreement": abs(
            candidate_scores.get("text_embed", 0.0) -
            candidate_scores.get("visual_embed", 0.0)
        ),
        "embed_gnn_agreement": abs(
            candidate_scores.get("embed", 0.0) -
            candidate_scores.get("gnn", 0.0)
        ),
        "all_signals_agree": (
            np.std(list(candidate_scores.values())) < 0.1
            if candidate_scores else False
        ),

        # === Query-Dependent Features ===
        "query_cmc": query_meta.get("cmc", 0),
        "query_is_creature": 1.0 if "Creature" in query_meta.get("types", []) else 0.0,
        "query_is_instant": 1.0 if "Instant" in query_meta.get("types", []) else 0.0,
        "query_is_sorcery": 1.0 if "Sorcery" in query_meta.get("types", []) else 0.0,
        "query_is_artifact": 1.0 if "Artifact" in query_meta.get("types", []) else 0.0,
        "query_is_enchantment": 1.0 if "Enchantment" in query_meta.get("types", []) else 0.0,

        # === Candidate-Dependent Features ===
        "candidate_cmc": candidate_meta.get("cmc", 0),
        "candidate_is_creature": 1.0 if "Creature" in candidate_meta.get("types", []) else 0.0,
        "candidate_is_instant": 1.0 if "Instant" in candidate_meta.get("types", []) else 0.0,
        "candidate_is_sorcery": 1.0 if "Sorcery" in candidate_meta.get("types", []) else 0.0,
        "candidate_is_artifact": 1.0 if "Artifact" in candidate_meta.get("types", []) else 0.0,
        "candidate_is_enchantment": 1.0 if "Enchantment" in candidate_meta.get("types", []) else 0.0,

        # === Query-Candidate Interaction ===
        "cmc_diff": abs(query_meta.get("cmc", 0) - candidate_meta.get("cmc", 0)),
        "cmc_same": 1.0 if query_meta.get("cmc", 0) == candidate_meta.get("cmc", 0) else 0.0,
        "same_type": 1.0 if (
            set(query_meta.get("types", [])) & set(candidate_meta.get("types", []))
        ) else 0.0,
        "same_colors": 1.0 if (
            set(query_meta.get("colors", [])) == set(candidate_meta.get("colors", []))
        ) else 0.0,
    }

    return features
```

## Reranking Phase

### Current (Manual Fusion)

```python
# Fixed weights, linear combination
final_score = (
    w_embed * embed_score +
    w_jaccard * jaccard_score +
    w_text * text_score +
    w_visual * visual_score +
    w_gnn * gnn_score
)
```

### Target (Learned Reranker)

```python
class LearnedReranker:
    """Learned reranker using gradient boosting."""

    def __init__(self, model_path: str | None = None):
        if model_path and Path(model_path).exists():
            self.model = self._load_model(model_path)
        else:
            self.model = None

    def rerank(
        self,
        query: str,
        candidates: list[str],
        feature_extractor: Callable,
    ) -> list[tuple[str, float]]:
        """Rerank candidates using learned model."""
        if self.model is None:
            raise ValueError("Model not loaded. Train or load a model first.")

        # Extract features for all query-candidate pairs
        features_list = [
            feature_extractor(query, candidate)
            for candidate in candidates
        ]

        # Convert to DataFrame for model
        import pandas as pd
        df = pd.DataFrame(features_list)

        # Predict relevance scores
        scores = self.model.predict(df.values)

        # Sort by predicted score
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True
        )
        return ranked

    def train(
        self,
        training_data: pd.DataFrame,
        method: str = "lightgbm",
        **kwargs
    ) -> None:
        """Train reranker on labeled data."""
        # Prepare features and labels
        feature_cols = [
            col for col in training_data.columns
            if col not in ["query", "candidate", "relevance"]
        ]
        X = training_data[feature_cols].values
        y = training_data["relevance"].values

        # Group by query (required for ranking models)
        groups = training_data.groupby("query").size().values

        # Train model
        if method == "lightgbm":
            import lightgbm as lgb
            self.model = lgb.LGBMRanker(
                objective="lambdarank",  # Optimizes NDCG directly
                n_estimators=kwargs.get("n_estimators", 200),
                max_depth=kwargs.get("max_depth", 6),
                learning_rate=kwargs.get("learning_rate", 0.05),
                metric="ndcg@10",
                random_state=42,
                verbose=-1,
            )
            self.model.fit(X, y, group=groups)

        elif method == "xgboost":
            import xgboost as xgb
            self.model = xgb.XGBRanker(
                objective="rank:pairwise",
                n_estimators=kwargs.get("n_estimators", 200),
                max_depth=kwargs.get("max_depth", 6),
                learning_rate=kwargs.get("learning_rate", 0.05),
                random_state=42,
            )
            self.model.fit(X, y, group=groups)

        else:
            raise ValueError(f"Unknown method: {method}")

    def save(self, path: str) -> None:
        """Save trained model."""
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    def _load_model(self, path: str):
        """Load trained model."""
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
```

## Two-Stage Pipeline

### Architecture

```python
class HybridSearchWithReranking:
    """Two-stage search: fast retrieval → learned reranking."""

    def __init__(
        self,
        retriever: WeightedLateFusion,  # Stage 1: Fast retrieval
        reranker: LearnedReranker | None = None,  # Stage 2: Learned reranking
        top_k_retrieve: int = 100,  # Retrieve more candidates
        top_k_final: int = 10,  # Final results after reranking
        use_reranking: bool = True,  # Toggle reranking on/off
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.top_k_retrieve = top_k_retrieve
        self.top_k_final = top_k_final
        self.use_reranking = use_reranking and reranker is not None

    def search(self, query: str) -> list[tuple[str, float]]:
        """Search with optional reranking."""
        # Stage 1: Fast retrieval (use current fusion for speed)
        candidates = self.retriever.similar(query, k=self.top_k_retrieve)

        if not self.use_reranking or not candidates:
            # Fallback to manual fusion results
            return candidates[:self.top_k_final]

        # Stage 2: Learned reranking (use LTR for quality)
        reranked = self.reranker.rerank(
            query=query,
            candidates=[c[0] for c in candidates],
            feature_extractor=lambda q, c: extract_all_features(q, c, self.retriever)
        )

        return reranked[:self.top_k_final]
```

## Implementation Plan

### Phase 1: Enhance Feature Extraction (Immediate)

1. ✅ **Extend `_compute_similarity_scores`** to also return rank positions
2. ✅ **Add `extract_all_features` function** with comprehensive feature set
3. ✅ **Add aggregation features** (max, min, mean, variance, range)
4. ✅ **Add query-dependent features** (card type, CMC, format)
5. ✅ **Add cross-modal agreement features**

### Phase 2: Create LearnedReranker Class (Short-term)

1. ✅ **Create `LearnedReranker` class** in `src/ml/reranking/`
2. ✅ **Integrate with existing LTR scripts** (reuse training logic)
3. ✅ **Add model save/load functionality**
4. ✅ **Support LightGBM and XGBoost**

### Phase 3: Two-Stage Pipeline (Medium-term)

1. ✅ **Create `HybridSearchWithReranking` class**
2. ✅ **Integrate into API** (optional reranking stage)
3. ✅ **Fallback to manual fusion** if reranker not available
4. ✅ **A/B test** manual vs learned reranking

### Phase 4: Evaluation and Optimization (Long-term)

1. ⏳ **Train reranker on full test set** with all features
2. ⏳ **Evaluate reranker vs manual fusion** (P@10, NDCG@10, MRR)
3. ⏳ **Feature importance analysis** (which features matter most?)
4. ⏳ **Hyperparameter tuning** (model depth, learning rate, etc.)
5. ⏳ **Continuous learning** (retrain on new labeled data)

## Key Differences: Manual Fusion vs. Learned Reranking

| Aspect | Manual Fusion | Learned Reranking |
|--------|---------------|-------------------|
| **Weights** | Fixed or grid-searched | Learned from data |
| **Feature Interactions** | None (linear only) | Can learn complex interactions |
| **Query Adaptation** | Same weights for all | Can adapt to query context |
| **Non-linearity** | Linear combination | Non-linear (gradient boosting) |
| **Training Data** | Not needed | Required (labeled pairs) |
| **Latency** | Fast (~10-50ms) | Slower (~50-200ms) |
| **Interpretability** | High (explicit weights) | Medium (feature importance) |
| **Maintenance** | Manual tuning | Retrain periodically |

## Recommendation

**Hybrid Approach** (Best of Both Worlds):

1. **Use manual fusion for Stage 1** (fast retrieval of top 100)
2. **Use learned reranking for Stage 2** (rerank top 100 to top 10)
3. **Fallback to manual fusion** if reranker unavailable
4. **A/B test** to measure improvement

This gives us:
- ✅ Fast initial retrieval (manual fusion)
- ✅ High-quality final ranking (learned reranking)
- ✅ Robustness (fallback if reranker fails)
- ✅ Measurable improvement (A/B test)

## Next Steps

1. **Implement comprehensive feature extraction** (Phase 1)
2. **Create LearnedReranker class** (Phase 2)
3. **Integrate two-stage pipeline** (Phase 3)
4. **Train and evaluate** (Phase 4)

The key insight: **Separate feature extraction from reranking, and learn the optimal combination instead of manually tuning weights.**
