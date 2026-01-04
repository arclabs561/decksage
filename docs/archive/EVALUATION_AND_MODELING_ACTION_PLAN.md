# Evaluation & Modeling Action Plan

**Date**: 2025-01-27
**Status**: 📋 **READY FOR EXECUTION**

---

## Executive Summary

Comprehensive analysis reveals **critical gaps** in evaluation, training, and modeling. This document provides a prioritized action plan to address all identified issues.

---

## 🔴 Priority 1: Evaluation System (CRITICAL)

### Status: ❌ Missing IAA System

**What's Done**:
- ✅ Basic evaluation metrics (P@K, nDCG, MRR)
- ✅ Bootstrap confidence intervals
- ✅ LLM-as-Judge (single judge)
- ✅ A/B testing framework

**What's Missing**:
- ❌ Inter-Annotator Agreement (IAA) - **JUST IMPLEMENTED** ✅
- ❌ Multi-judge LLM consensus
- ❌ Test set expansion (only 5-13 queries per game)
- ❌ Confidence calibration

### Action Items

#### ✅ Task 1.1: IAA System (COMPLETE)
- **File**: `src/ml/evaluation/inter_annotator_agreement.py` ✅
- **Features**:
  - Cohen's Kappa (two annotators)
  - Krippendorff's Alpha (multiple annotators, missing data)
  - Fleiss' Kappa (multiple annotators, categorical)
  - Intra-annotator agreement (stability)
  - Confidence analysis

**Next**: Integrate into annotation pipeline

#### Task 1.2: Multi-Judge LLM System (TODO)
**File**: `src/ml/evaluation/multi_judge_llm.py` (to create)

**Implementation**:
```python
class MultiJudgeLLM:
    """Ensemble of LLM judges with agreement analysis."""

    def __init__(self, models: list[str] = None):
        self.models = models or [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-pro-1.5"
        ]

    def judge_with_consensus(self, query: str, candidate: str) -> dict:
        """Get judgments from all judges, compute consensus and IAA."""
        # 1. Get judgments from all models
        # 2. Compute Krippendorff's Alpha
        # 3. Compute consensus (median or weighted)
        # 4. Return with agreement metrics
        pass
```

**Integration Points**:
- `src/ml/annotation/llm_judge_batch.py` - Add multi-judge option
- `src/ml/evaluation/ab_testing.py` - Include IAA in reports

#### Task 1.3: Test Set Expansion (TODO)
**File**: `src/ml/scripts/expand_test_sets.py` (to create)

**Goal**: Expand from 5-13 queries to **50-100 queries per game**

**Method**:
1. Use LLM-as-Judge to generate draft annotations (100+ queries)
2. Human review and refinement (stratified sampling)
3. Compute IAA on expanded set
4. Validate coverage (card types, archetypes, formats)

**Output**:
- `experiments/test_set_expanded_magic.json` (50+ queries)
- `experiments/test_set_expanded_pokemon.json` (50+ queries)
- `experiments/test_set_expanded_yugioh.json` (50+ queries)

---

## 🟡 Priority 2: Training Completion (HIGH)

### Status: ⚠️ Not Completed

**What's Done**:
- ✅ GNN implementation complete
- ✅ Signal computation scripts ready
- ✅ Training scripts ready

**What's Missing**:
- ❌ GNN models not trained
- ❌ Signals not computed
- ❌ Full evaluation not run

### Action Items

#### Task 2.1: Compute All Signals (TODO)
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

**Expected Output**:
- `experiments/signals/sideboard_cooccurrence.json`
- `experiments/signals/temporal_cooccurrence.json`
- `experiments/signals/archetype_staples.json`
- `experiments/signals/archetype_cooccurrence.json`
- `experiments/signals/format_cooccurrence.json`
- `experiments/signals/cross_format_patterns.json`

#### Task 2.2: Train GNN Models (TODO)
```bash
uv run python -m src.ml.scripts.train_gnn \
  --model GraphSAGE \
  --epochs 100 \
  --early-stopping-patience 10 \
  --output experiments/signals/gnn_embeddings.json
```

**Expected Output**:
- `experiments/signals/gnn_embeddings.json`
- Model checkpoint (optional)

#### Task 2.3: Full Evaluation Pipeline (TODO)
```bash
# Run evaluation on all models
uv run python -m src.ml.evaluation.compare_models \
  --test-set experiments/test_set_canonical_magic.json \
  --embeddings data/embeddings/*.wv \
  --output experiments/evaluation_report.json
```

---

## 🟢 Priority 3: Modeling Improvements (MEDIUM)

### Status: ⚠️ Could Be Improved

**What's Done**:
- ✅ Multi-modal fusion (9 signals)
- ✅ Multiple aggregation methods
- ✅ GNN implementation (GraphSAGE)

**What's Missing**:
- ❌ Node similarity-based convolution
- ❌ Explainability system
- ❌ Single-layer GCN option (for stability)

### Action Items

#### Task 3.1: Node Similarity-Based Convolution (TODO)
**Research Finding**: Node similarity-based convolution outperforms standard adjacency for link prediction.

**File**: `src/ml/similarity/gnn_similarity_conv.py` (to create)

**Implementation**:
- Compute similarity matrices (Jaccard, CN, Adamic-Adar, Sorenson)
- Use similarity matrix instead of adjacency in GNN
- Validate against standard approach

#### Task 3.2: Explainability System (TODO)
**Research Finding**: Gradient-based explanations outperform mutual information.

**File**: `src/ml/similarity/explainability.py` (to create)

**Features**:
- Gradient-based attribution for similarity scores
- Edge importance visualization
- Signal contribution analysis

---

## 📊 Data Needs Assessment

### Current Data Inventory

**Available**:
- ✅ Deck co-occurrence data
- ✅ Card metadata
- ✅ Archetype labels
- ✅ Format labels
- ✅ Temporal data

**Missing**:
- ❌ Tournament results (win rates, matchups, meta share)
- ❌ Large-scale test sets (50-100+ queries per game)
- ❌ Player metadata

### Data Acquisition Priorities

**T1: Test Set Expansion** (CRITICAL - see Task 1.3)

**T2: Tournament Results** (HIGH)
- **Action**: Scrape tournament results
- **Sources**: MTGTop8, MTGGoldfish, Pokemon.com
- **Data**: Win rates, matchup data, meta share
- **File**: `src/backend/cmd/scrape-tournaments/` (to create)

**T3: Synthetic Judging** (MEDIUM)
- **Action**: Use LLM-as-Judge to generate 1000+ query-candidate pairs
- **Validation**: Human review on 10-20% subset
- **File**: `src/ml/scripts/generate_synthetic_test_set.py` (to create)

---

## 🎯 Success Metrics

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

## 📅 Recommended Timeline

### Week 1: Evaluation Foundation
- ✅ Day 1-2: IAA system (DONE)
- Day 3-4: Multi-judge LLM system
- Day 5: Test set expansion (LLM generation)

### Week 2: Training & Signals
- Day 1-2: Compute all signals
- Day 3-4: Train GNN models
- Day 5: Full evaluation pipeline

### Week 3: Modeling Improvements
- Day 1-3: Node similarity-based convolution
- Day 4-5: Explainability system

### Week 4: Data Acquisition
- Day 1-3: Tournament results scraping
- Day 4-5: Synthetic test set generation

---

## 📁 Files Created/Modified

### ✅ Created
1. `src/ml/evaluation/inter_annotator_agreement.py` - IAA metrics ✅
2. `COMPREHENSIVE_EVALUATION_ANALYSIS.md` - Full analysis ✅
3. `EVALUATION_AND_MODELING_ACTION_PLAN.md` - This file ✅

### 📝 To Create
1. `src/ml/evaluation/multi_judge_llm.py` - Multi-judge consensus
2. `src/ml/scripts/expand_test_sets.py` - Test set expansion
3. `src/ml/similarity/gnn_similarity_conv.py` - Similarity-based convolution
4. `src/ml/similarity/explainability.py` - Gradient-based explanations
5. `src/backend/cmd/scrape-tournaments/` - Tournament scraping

### 🔧 To Modify
1. `src/ml/annotation/llm_judge_batch.py` - Add multi-judge support
2. `src/ml/evaluation/ab_testing.py` - Include IAA in reports
3. `src/ml/similarity/gnn_embeddings.py` - Add similarity-based convolution option

---

## 🚀 Quick Start

### Immediate Actions (Today)

1. **Test IAA System**:
```python
from src.ml.evaluation.inter_annotator_agreement import InterAnnotatorAgreement

iaa = InterAnnotatorAgreement()
result = iaa.cohens_kappa([4, 3, 2, 1, 0], [4, 3, 2, 1, 0])
print(result)  # Should show kappa=1.0 (perfect agreement)
```

2. **Compute Signals**:
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

3. **Train GNN**:
```bash
uv run python -m src.ml.scripts.train_gnn --model GraphSAGE --epochs 100
```

---

**Status**: ✅ **IAA SYSTEM IMPLEMENTED** - Ready for integration and testing!
