# Comprehensive Evaluation & Modeling Analysis

**Date**: 2025-01-27
**Status**: 🔍 **CRITICAL GAPS IDENTIFIED** - Action Required

---

## Executive Summary

After thorough analysis of evaluation systems, modeling design, training status, and data needs, **critical gaps** have been identified:

1. ❌ **No Inter-Annotator Agreement (IAA) System** - Missing modern best practices
2. ⚠️ **Insufficient Test Sets** - Only 5-13 queries per game (need 50-100+)
3. ⚠️ **GNN Training Not Completed** - Models exist but not trained
4. ⚠️ **Evaluation Lacks Statistical Rigor** - Missing IAA, calibration, multi-judge validation
5. ⚠️ **Modeling Design Could Be Improved** - Missing node similarity-based convolution, explainability

---

## 1. Evaluation System Assessment

### ✅ What We Have

**Current Evaluation Infrastructure**:
- `src/ml/utils/evaluation.py` - Basic metrics (P@K, nDCG, MRR)
- `src/ml/utils/evaluation_with_ci.py` - Bootstrap confidence intervals ✅
- `src/ml/evaluation/ab_testing.py` - A/B testing framework ✅
- `src/ml/annotation/llm_judge_batch.py` - LLM-as-Judge system ✅
- Test sets: 3 canonical sets (Magic: 5 queries, Pokemon: 10, Yu-Gi-Oh: 13)

**Strengths**:
- ✅ Bootstrap confidence intervals implemented
- ✅ Multiple metrics (P@K, nDCG, MRR)
- ✅ LLM-as-Judge for scale
- ✅ A/B testing framework

### ❌ Critical Gaps

#### 1.1 Missing Inter-Annotator Agreement (IAA)

**Status**: ❌ **NOT IMPLEMENTED**

**What's Missing**:
- No Cohen's Kappa computation
- No Krippendorff's Alpha (multi-annotator)
- No intra-annotator agreement (stability)
- No annotator confidence tracking
- No disagreement analysis

**Best Practices (2024-2025)**:
1. **Multi-layered evaluation**: Assess annotator reliability, sample difficulty, label ambiguity simultaneously
2. **Intra-annotator agreement**: Complement IAA with stability checks
3. **Annotator confidence**: Incorporate confidence ratings
4. **Continuous monitoring**: Track IAA trends over time
5. **Granularity considerations**: Fine-grained annotation improves agreement

**Impact**: Cannot validate annotation quality or detect systematic errors.

#### 1.2 Insufficient Test Set Coverage

**Current State**:
- Magic: **5 queries** (need 50-100+)
- Pokemon: **10 queries** (need 50-100+)
- Yu-Gi-Oh: **13 queries** (need 50-100+)

**Problems**:
- Statistical significance impossible with n=5
- Cannot detect improvements reliably
- Limited coverage of card types/archetypes
- No cross-game evaluation possible

**Recommendation**: Expand to **50-100 queries per game** with:
- Stratified sampling (card types, rarities, archetypes)
- Balanced difficulty distribution
- Metadata (source, annotation method, date)

#### 1.3 LLM-as-Judge Lacks Validation

**Current State**:
- Single LLM judge (Claude 3.5 Sonnet)
- No calibration against human annotations
- No multi-judge consensus
- No confidence calibration

**Best Practices Missing**:
- **Multi-judge ensemble**: Use 3+ LLM judges, compute agreement
- **Calibration**: Validate against human annotations on subset
- **Confidence calibration**: Map confidence scores to actual accuracy
- **Adversarial testing**: Test on edge cases

---

## 2. Inter-Annotator Agreement System Design

### 2.1 Required Components

**Core Metrics**:
1. **Cohen's Kappa** (κ) - Two annotators, categorical
2. **Krippendorff's Alpha** (α) - Multiple annotators, handles missing data
3. **Intra-class Correlation** (ICC) - Continuous/ordinal annotations
4. **Fleiss' Kappa** - Multiple annotators, categorical

**Implementation Plan**:

```python
# src/ml/evaluation/inter_annotator_agreement.py

class InterAnnotatorAgreement:
    """Compute IAA metrics for annotation quality assessment."""

    def cohens_kappa(self, annotator1: list[int], annotator2: list[int]) -> float:
        """Cohen's Kappa for two annotators."""
        # κ = (P_o - P_e) / (1 - P_e)
        # P_o = observed agreement
        # P_e = expected agreement by chance
        pass

    def krippendorffs_alpha(
        self,
        annotations: dict[str, list[int]],  # annotator -> ratings
        metric: str = "nominal"  # nominal|ordinal|interval|ratio
    ) -> float:
        """Krippendorff's Alpha for multiple annotators."""
        # Handles missing data, different metric types
        pass

    def intra_annotator_agreement(
        self,
        annotator: str,
        annotations1: list[int],
        annotations2: list[int],
        time_interval: float
    ) -> dict[str, float]:
        """Intra-annotator agreement (stability over time)."""
        # Same annotator, same items, different times
        pass

    def annotator_confidence_analysis(
        self,
        annotations: list[dict]  # {rating, confidence, reasoning}
    ) -> dict[str, float]:
        """Analyze relationship between confidence and agreement."""
        pass
```

**Integration Points**:
- `src/ml/annotation/annotate.py` - Add IAA computation
- `src/ml/annotation/llm_judge_batch.py` - Multi-judge consensus
- `src/ml/evaluation/ab_testing.py` - Include IAA in reports

### 2.2 Multi-Judge LLM System

**Design**:
```python
# src/ml/evaluation/multi_judge_llm.py

class MultiJudgeLLM:
    """Ensemble of LLM judges with agreement analysis."""

    def __init__(self, models: list[str] = None):
        self.models = models or [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-pro-1.5"
        ]
        self.judges = [make_judge_agent(m) for m in self.models]

    def judge_with_consensus(
        self,
        query: str,
        candidate: str
    ) -> dict[str, Any]:
        """Get judgments from all judges, compute consensus."""
        judgments = [j.run_sync(prompt) for j in self.judges]

        # Compute agreement
        ratings = [j.output.relevance for j in judgments]
        kappa = self.compute_agreement(ratings)

        # Consensus: median or weighted by confidence
        consensus_rating = self.compute_consensus(judgments)

        return {
            "consensus_rating": consensus_rating,
            "agreement": kappa,
            "judgments": judgments,
            "confidence": self.compute_confidence(judgments)
        }
```

---

## 3. Modeling Design Review

### 3.1 Current Architecture

**Multi-Modal Fusion** (9 signals):
1. Embedding (Node2Vec/PecanPy)
2. Jaccard (co-occurrence)
3. Functional tags
4. Text embeddings
5. Sideboard co-occurrence
6. Temporal trends
7. GNN embeddings (GraphSAGE)
8. Archetype staples
9. Format patterns

**Aggregation Methods**:
- Weighted linear combination
- Reciprocal Rank Fusion (RRF)
- CombSum, CombMax, CombMin
- Maximal Marginal Relevance (MMR)

### 3.2 Gaps vs. Best Practices

#### ❌ Missing: Node Similarity-Based Convolution

**Research Finding**: Node similarity-based convolution matrices outperform standard adjacency matrices for link prediction.

**Current**: Using standard adjacency matrix for GNN
**Should Use**: Node similarity-based convolution (CN, Jaccard, Adamic-Adar, etc.)

**Implementation**:
```python
# src/ml/similarity/gnn_embeddings.py

def compute_node_similarity_matrix(
    edge_index: torch.Tensor,
    similarity_metric: str = "jaccard"  # jaccard|cn|adamic_adar|sorenson
) -> torch.Tensor:
    """Compute node similarity-based convolution matrix."""
    # Instead of A (adjacency), use S (similarity)
    # Sorenson Index, Hub-Promoted Index, Common Neighbors show best results
    pass
```

#### ⚠️ Missing: Explainability

**Research Finding**: Gradient-based explanations outperform mutual information for similarity scores.

**Current**: No explainability
**Should Add**: Gradient-based attribution for similarity scores

**Implementation**:
```python
# src/ml/similarity/explainability.py

class SimilarityExplainer:
    """Explain similarity scores using gradient-based methods."""

    def explain_similarity(
        self,
        query: str,
        candidate: str,
        fusion_model: WeightedLateFusion
    ) -> dict[str, Any]:
        """Compute gradient-based attribution for edges."""
        # Which edges contribute most to similarity?
        # Which signals contribute most?
        pass
```

#### ⚠️ Architecture: Should Use Single-Layer GCN

**Research Finding**: Single-layer GCN with node similarity-based convolution is more stable than deeper architectures.

**Current**: 2-layer GraphSAGE (configurable)
**Recommendation**: Add single-layer option, validate stability

---

## 4. Training Status

### 4.1 Current State

**Embeddings**:
- ✅ Node2Vec/PecanPy embeddings trained (multiple dimensions)
- ✅ Text embeddings (sentence-transformers) loaded
- ✅ Functional tags computed

**GNN**:
- ❌ **NOT TRAINED** - Code exists but no trained models
- ⚠️ Implementation complete but not executed
- ⚠️ No saved embeddings in `experiments/signals/gnn_embeddings.json`

**Signals**:
- ⚠️ Sideboard, temporal, archetype, format signals **not computed yet**
- ⚠️ Script exists (`compute_and_cache_signals.py`) but not run

### 4.2 Training Checklist

**Immediate Actions**:
1. ✅ Train GNN models (`train_gnn.py`)
2. ✅ Compute all signals (`compute_and_cache_signals.py`)
3. ✅ Validate embeddings quality
4. ✅ Run full evaluation pipeline

---

## 5. Data Needs Assessment

### 5.1 Current Data Inventory

**Available**:
- ✅ Deck co-occurrence data
- ✅ Card metadata (text, types, etc.)
- ✅ Archetype labels
- ✅ Format labels
- ✅ Temporal data (deck dates)

**Missing**:
- ❌ Tournament results (win rates, matchups)
- ❌ Matchup-specific patterns
- ❌ Player metadata
- ❌ Large-scale test sets (50-100+ queries per game)

### 5.2 Data Acquisition Priorities

**T1: Test Set Expansion** (CRITICAL):
- **Action**: Expand test sets to 50-100 queries per game
- **Method**:
  - LLM-as-Judge to generate draft annotations
  - Human review and refinement
  - Stratified sampling (card types, archetypes)

**T2: Tournament Results** (HIGH):
- **Action**: Scrape tournament results
- **Sources**: MTGTop8, MTGGoldfish, Pokemon.com
- **Data**: Win rates, matchup data, meta share

**T3: Synthetic Judging** (MEDIUM):
- **Action**: Use LLM-as-Judge to generate large-scale test sets
- **Scale**: 1000+ query-candidate pairs
- **Validation**: Human review on subset (10-20%)

---

## 6. Recommendations & Action Plan

### Priority 1: Evaluation System (CRITICAL)

**Week 1: Inter-Annotator Agreement**
1. Implement `InterAnnotatorAgreement` class
2. Add Cohen's Kappa, Krippendorff's Alpha
3. Integrate into annotation pipeline
4. Add IAA reporting to evaluation

**Week 2: Multi-Judge LLM System**
1. Implement `MultiJudgeLLM` ensemble
2. Add consensus computation
3. Validate against human annotations
4. Add confidence calibration

**Week 3: Test Set Expansion**
1. Use LLM-as-Judge to generate 50+ queries per game
2. Human review and refinement
3. Compute IAA on expanded set
4. Stratified sampling validation

### Priority 2: Training Completion (HIGH)

**Week 1: Signal Computation**
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

**Week 2: GNN Training**
```bash
uv run python -m src.ml.scripts.train_gnn \
  --model GraphSAGE \
  --epochs 100 \
  --output experiments/signals/gnn_embeddings.json
```

**Week 3: Full Evaluation**
- Run evaluation on all models
- Compare with/without GNN
- Statistical significance testing

### Priority 3: Modeling Improvements (MEDIUM)

**Month 1: Node Similarity-Based Convolution**
- Implement similarity matrix computation
- Update GNN to use similarity-based convolution
- Validate against standard adjacency

**Month 2: Explainability**
- Implement gradient-based explanations
- Add explanation API endpoint
- Visualize attribution

---

## 7. Success Metrics

### Evaluation System
- ✅ IAA > 0.75 (Cohen's Kappa) for human annotations
- ✅ Multi-judge LLM agreement > 0.70
- ✅ Test sets: 50+ queries per game
- ✅ Statistical significance: p < 0.05 for improvements

### Training
- ✅ All signals computed and cached
- ✅ GNN models trained and validated
- ✅ Full evaluation pipeline passing

### Modeling
- ✅ Node similarity-based convolution implemented
- ✅ Explainability system operational
- ✅ Performance improvement: P@10 > 0.15 (from 0.088)

---

## 8. Implementation Files Needed

### New Files
1. `src/ml/evaluation/inter_annotator_agreement.py` - IAA metrics
2. `src/ml/evaluation/multi_judge_llm.py` - Multi-judge consensus
3. `src/ml/similarity/gnn_similarity_conv.py` - Node similarity convolution
4. `src/ml/similarity/explainability.py` - Gradient-based explanations
5. `src/ml/scripts/expand_test_sets.py` - Test set expansion tool

### Modified Files
1. `src/ml/annotation/annotate.py` - Add IAA computation
2. `src/ml/annotation/llm_judge_batch.py` - Multi-judge support
3. `src/ml/similarity/gnn_embeddings.py` - Similarity-based convolution
4. `src/ml/evaluation/ab_testing.py` - Include IAA in reports

---

**Status**: 🔴 **ACTION REQUIRED** - Critical gaps identified, implementation plan ready.
