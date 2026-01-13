# Learning-to-Rank Critique and Refinement

**Date:** January 6, 2026
**Status:** Critical Analysis Complete - Architecture Refinement Needed

## Critical Insight: This IS a Learning-to-Rank Problem

You're absolutely right. We should be thinking about this as:

1. **Feature Extraction**: Compute similarity scores from each modality (text, visual, graph, etc.)
2. **Reranking**: Use a learned model to optimally combine features

Currently, we're doing **manual fusion** (weighted sum, RRF) instead of **learned reranking**.

## Current Architecture Critique

### What We're Doing Now (Manual Fusion)

```python
# Feature extraction (good)
scores = {
    "embed": 0.85,      # Co-occurrence similarity
    "jaccard": 0.72,   # Graph co-occurrence
    "text_embed": 0.91, # Text embedding similarity
    "visual_embed": 0.68, # Visual similarity
    "gnn": 0.79,       # GNN embedding similarity
}

# Manual fusion (problematic)
final_score = (
    w_embed * scores["embed"] +
    w_jaccard * scores["jaccard"] +
    w_text * scores["text_embed"] +
    w_visual * scores["visual_embed"] +
    w_gnn * scores["gnn"]
)
```

**Problems:**
1. ❌ **No learning**: Weights are manually tuned or grid-searched
2. ❌ **No feature interactions**: Can't learn that "high text + high visual" is better than sum
3. ❌ **Linear combination**: Can't capture non-linear relationships
4. ❌ **No query-dependent weighting**: Same weights for all queries
5. ❌ **No context awareness**: Doesn't adapt to query type or card characteristics

### What We Should Be Doing (Learned Reranking)

```python
# Feature extraction (same - this is good)
features = {
    "embed_score": 0.85,
    "jaccard_score": 0.72,
    "text_embed_score": 0.91,
    "visual_embed_score": 0.68,
    "gnn_score": 0.79,
    # Additional features
    "embed_rank": 3,           # Rank position in embedding list
    "jaccard_rank": 5,          # Rank position in Jaccard list
    "num_modalities": 5,        # How many signals agree
    "max_score": 0.91,          # Best single signal
    "min_score": 0.68,          # Worst single signal
    "score_variance": 0.008,    # Agreement between signals
}

# Learned reranking (better)
final_score = learned_model.predict(features)
```

**Advantages:**
1. ✅ **Learns optimal combination**: Model learns from labeled data
2. ✅ **Feature interactions**: Can learn complex relationships
3. ✅ **Non-linear**: Gradient boosting can capture non-linear patterns
4. ✅ **Query-dependent**: Can include query features (task type, card type, etc.)
5. ✅ **Context-aware**: Can adapt to different scenarios

## Feature Extraction → Reranking Flow

### Phase 1: Feature Extraction (Current - Good ✅)

```python
def extract_features(query: str, candidate: str) -> dict[str, float]:
    """Extract all similarity features for query-candidate pair."""
    return {
        # Direct similarity scores
        "embed_score": compute_embedding_similarity(query, candidate),
        "jaccard_score": compute_jaccard_similarity(query, candidate),
        "text_embed_score": compute_text_embedding_similarity(query, candidate),
        "visual_embed_score": compute_visual_embedding_similarity(query, candidate),
        "gnn_score": compute_gnn_similarity(query, candidate),
        "functional_score": compute_functional_similarity(query, candidate),

        # Rank-based features (for RRF-style methods)
        "embed_rank": get_rank_in_embedding_list(query, candidate),
        "jaccard_rank": get_rank_in_jaccard_list(query, candidate),
        "text_embed_rank": get_rank_in_text_list(query, candidate),
        "visual_embed_rank": get_rank_in_visual_list(query, candidate),
        "gnn_rank": get_rank_in_gnn_list(query, candidate),

        # Aggregation features
        "num_modalities": count_available_modalities(query, candidate),
        "max_score": max(all_scores),
        "min_score": min(all_scores),
        "mean_score": mean(all_scores),
        "score_variance": variance(all_scores),
        "score_range": max_score - min_score,

        # Query-dependent features
        "query_card_type": get_card_type(query),
        "candidate_card_type": get_card_type(candidate),
        "same_type": query_card_type == candidate_card_type,
        "query_cmc": get_cmc(query),
        "candidate_cmc": get_cmc(candidate),
        "cmc_diff": abs(query_cmc - candidate_cmc),

        # Cross-modal features
        "text_visual_agreement": abs(text_score - visual_score),
        "embed_gnn_agreement": abs(embed_score - gnn_score),
        "all_agree": all_scores_similar(all_scores, threshold=0.1),
    }
```

### Phase 2: Reranking (Missing - Needs Implementation ⚠️)

```python
class LearnedReranker:
    """Learned reranker using gradient boosting (XGBoost/LightGBM)."""

    def __init__(self, model_path: str | None = None):
        self.model = self._load_model(model_path) if model_path else None

    def rerank(
        self,
        query: str,
        candidates: list[str],
        feature_extractor: Callable
    ) -> list[tuple[str, float]]:
        """Rerank candidates using learned model."""
        # Extract features for all query-candidate pairs
        features_list = [
            feature_extractor(query, candidate)
            for candidate in candidates
        ]

        # Predict relevance scores
        scores = self.model.predict(features_list)

        # Sort by predicted score
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True
        )
        return ranked

    def train(
        self,
        training_data: pd.DataFrame,  # query, candidate, relevance, features...
        method: str = "lightgbm"
    ):
        """Train reranker on labeled data."""
        # Prepare features and labels
        feature_cols = [col for col in training_data.columns
                       if col not in ["query", "candidate", "relevance"]]
        X = training_data[feature_cols].values
        y = training_data["relevance"].values

        # Group by query (required for ranking models)
        groups = training_data.groupby("query").size().values

        # Train model
        if method == "lightgbm":
            model = lgb.LGBMRanker(
                objective="lambdarank",  # Optimizes NDCG directly
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                metric="ndcg@10",
            )
            model.fit(X, y, group=groups)
            self.model = model
```

## What We Already Have (Good News!)

We actually **do have** some LTR infrastructure, but it's **not properly integrated**:

1. ✅ **`scripts/optimization/learned_fusion_weights.py`**
   - Uses XGBoost/LightGBM for ranking
   - Extracts features from test set
   - Trains ranking models
   - **BUT**: Only extracts 3 features (embed, jaccard, text_embed)
   - **BUT**: Extracts weights from feature importance (not true reranking)
   - **BUT**: Not integrated into main pipeline

2. ✅ **`scripts/optimization/enhanced_learned_fusion.py`**
   - Enhanced version with more features (score differences, max/min, CMC, card types)
   - Uses LightGBM with LambdaRank (optimizes NDCG directly)
   - **BUT**: Still extracts weights instead of using model for reranking
   - **BUT**: Not integrated into main pipeline

3. ❌ **`WeightedLateFusion` (main pipeline)**
   - Does manual fusion (weighted sum, RRF)
   - No learned reranking
   - No feature extraction for LTR

## What's Missing (Critical Gaps)

### 1. Feature Extraction is Incomplete

**Current**: Only extracts similarity scores
```python
features = {
    "embed_score": 0.85,
    "jaccard_score": 0.72,
    "text_embed_score": 0.91,
}
```

**Should Extract**:
- ✅ Similarity scores (current)
- ❌ Rank positions (missing)
- ❌ Aggregation features (missing)
- ❌ Query-dependent features (missing)
- ❌ Cross-modal agreement (missing)

### 2. No Integrated Reranking Pipeline

**Current**: Manual fusion in `WeightedLateFusion`
```python
# Manual weighted sum
final_score = weighted_sum(scores, weights)
```

**Should Have**:
- ✅ Feature extraction (exists but incomplete)
- ❌ Learned reranker (exists but not integrated)
- ❌ Two-stage pipeline: retrieve → rerank

### 3. No Query-Dependent Features

**Current**: Same weights for all queries
```python
weights = FusionWeights(...)  # Fixed for all queries
```

**Should Have**:
- Query type (substitution, synergy, meta)
- Card type (creature, spell, artifact)
- CMC range
- Format context

## Refined Architecture

### Two-Stage Pipeline

```python
class HybridSearchWithReranking:
    """Two-stage search: retrieve → rerank."""

    def __init__(
        self,
        retriever: WeightedLateFusion,  # Stage 1: Fast retrieval
        reranker: LearnedReranker,       # Stage 2: Learned reranking
        top_k_retrieve: int = 100,      # Retrieve more, rerank top
        top_k_final: int = 10,           # Final results
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.top_k_retrieve = top_k_retrieve
        self.top_k_final = top_k_final

    def search(self, query: str) -> list[tuple[str, float]]:
        # Stage 1: Fast retrieval (use current fusion for speed)
        candidates = self.retriever.similar(query, k=self.top_k_retrieve)

        # Stage 2: Learned reranking (use LTR for quality)
        reranked = self.reranker.rerank(
            query=query,
            candidates=[c[0] for c in candidates],
            feature_extractor=self._extract_all_features
        )

        return reranked[:self.top_k_final]

    def _extract_all_features(self, query: str, candidate: str) -> dict:
        """Extract comprehensive feature set."""
        # Get all similarity scores
        scores = self.retriever._compute_similarity_scores(query, {candidate})

        # Extract comprehensive features
        return {
            # Direct scores
            **{f"{k}_score": v for k, v in scores[candidate].items()},

            # Rank positions (need to compute)
            **self._get_rank_features(query, candidate),

            # Aggregation features
            **self._get_aggregation_features(scores[candidate]),

            # Query-dependent features
            **self._get_query_features(query, candidate),

            # Cross-modal agreement
            **self._get_agreement_features(scores[candidate]),
        }
```

## Implementation Plan

### Phase 1: Enhance Feature Extraction (Immediate)

1. **Extend `_compute_similarity_scores`** to also return rank positions
2. **Add aggregation features** (max, min, mean, variance, range)
3. **Add query-dependent features** (card type, CMC, format)
4. **Add cross-modal agreement features**

### Phase 2: Integrate Learned Reranker (Short-term)

1. **Create `LearnedReranker` class** that wraps existing LTR scripts
2. **Integrate into `WeightedLateFusion`** as optional reranking stage
3. **Two-stage pipeline**: Fast retrieval → Learned reranking
4. **Fallback to manual fusion** if reranker not available

### Phase 3: Full LTR Pipeline (Medium-term)

1. **Train reranker on full test set** with all features
2. **Evaluate reranker vs manual fusion** (P@10, NDCG@10)
3. **A/B test in production** (if applicable)
4. **Continuous learning** (retrain on new labeled data)

## Critical Questions to Answer

1. **Do we have enough labeled data?**
   - Current test set: ~100 queries?
   - Need: 1000+ query-document pairs for robust LTR

2. **Should we use pointwise, pairwise, or listwise?**
   - **Pointwise**: Treat as regression (simpler)
   - **Pairwise**: Learn relative ordering (better for ranking)
   - **Listwise**: Optimize NDCG directly (best, but complex)
   - **Recommendation**: Start with pairwise (LambdaRank), move to listwise if needed

3. **What's the latency budget?**
   - Manual fusion: ~10-50ms
   - Learned reranking: ~50-200ms (feature extraction + model inference)
   - **Recommendation**: Two-stage (fast retrieval → rerank top 100)

4. **How often to retrain?**
   - Static: Train once, deploy
   - Periodic: Retrain monthly/quarterly
   - Online: Continuous learning (complex)

## Conclusion

**Current State**: Manual fusion (good baseline, but suboptimal)
**Target State**: Learned reranking (better quality, requires infrastructure)

**Next Steps**:
1. ✅ Enhance feature extraction (add rank, aggregation, query features)
2. ✅ Integrate existing LTR scripts into main pipeline
3. ✅ Two-stage pipeline: retrieve → rerank
4. ⏳ Evaluate learned vs manual fusion
5. ⏳ Production deployment (if applicable)

The key insight: **We're already doing feature extraction, we just need to learn how to combine them optimally instead of manually.**
