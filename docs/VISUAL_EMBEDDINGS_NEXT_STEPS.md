# Visual Embeddings: Next Steps

**Date**: January 2026  
**Status**: Integration complete, ready for evaluation and optimization

## Completed ✅

1. ✅ Core visual embedder implementation
2. ✅ Full fusion system integration
3. ✅ API integration
4. ✅ Search/indexing support
5. ✅ Enrichment pipeline updates
6. ✅ Comprehensive testing suite
7. ✅ Complete documentation
8. ✅ Task-specific weights updated
9. ✅ Hybrid embeddings integration updated

## Recommended Next Steps

### 1. Evaluation and Benchmarking (HIGH PRIORITY)

**Goal**: Measure actual impact of visual embeddings on similarity search quality.

**Actions**:
```bash
# Run evaluation comparing with/without visual embeddings
python3 scripts/evaluation/evaluate_visual_embeddings.py \
    --test-set data/test_set_minimal.json \
    --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
    --pairs data/pairs/magic_large.csv \
    --top-k 10 \
    --output experiments/visual_embeddings_evaluation.json
```

**Metrics to Track**:
- P@10 improvement
- NDCG@10 improvement
- Recall@10 improvement
- Per-query analysis (which queries benefit most)

**Expected Outcome**: Quantify improvement from visual embeddings (target: +5-10% P@10)

### 2. Ablation Study (HIGH PRIORITY)

**Goal**: Understand contribution of each modality.

**Actions**:
- Run evaluation with different weight combinations
- Measure performance with visual embeddings at 0%, 10%, 20%, 30% weight
- Compare against text embeddings, GNN, co-occurrence

**Script**: Create `scripts/evaluation/visual_embeddings_ablation.py`

### 3. Update Optimization Scripts (MEDIUM PRIORITY)

**Goal**: Ensure optimization scripts include visual embeddings.

**Scripts to Update**:
- `src/ml/scripts/optimize_fusion_for_substitution.py`
- `src/ml/scripts/optimize_fusion_all_aggregators.py`
- `src/ml/scripts/optimize_fusion_for_similarity.py`

**Pattern**:
```python
# Load visual embedder if available
visual_embedder = None
try:
    from ml.similarity.visual_embeddings import get_visual_embedder
    visual_embedder = get_visual_embedder()
except (ImportError, Exception):
    pass

# Include in fusion
fusion = WeightedLateFusion(
    ...,
    visual_embedder=visual_embedder,
)
```

**Priority**: Medium (scripts work without it, but should include for completeness)

### 4. Downstream Task Evaluation (MEDIUM PRIORITY)

**Goal**: Measure impact on substitution and deck completion tasks.

**Actions**:
- Run `evaluate_downstream_complete.py` with visual embeddings enabled
- Compare substitution P@10 with/without visual
- Measure deck completion quality

**Expected Outcome**: Visual embeddings may help identify reprints and alternate art for substitution

### 5. Image Coverage Analysis (LOW PRIORITY)

**Goal**: Understand visual embedding coverage across games.

**Actions**:
- Analyze % of cards with image URLs per game
- Identify games/formats with low coverage
- Prioritize image collection for high-value cards

**Script**: Create `scripts/analysis/visual_embedding_coverage.py`

### 6. Fine-Tuning Preparation (FUTURE)

**Goal**: Prepare for fine-tuning SigLIP 2 on trading card images.

**Actions**:
- Collect card image datasets using `collect_card_images.py`
- Organize images by game, set, rarity
- Create training/validation splits
- Fine-tune model on card-specific data

**Expected Outcome**: 10-20% improvement over pre-trained model

### 7. Performance Optimization (FUTURE)

**Goal**: Optimize visual embedding generation for production.

**Actions**:
- Profile embedding generation latency
- Optimize batch processing
- Consider model quantization
- Cache frequently-accessed embeddings

**Target**: <100ms per embedding (batch of 10)

## Immediate Actions

1. **Run evaluation** to measure impact
2. **Update optimization scripts** to include visual embeddings
3. **Document results** in evaluation report

## Success Criteria

- ✅ Visual embeddings integrated and working
- ⏳ P@10 improvement measured and documented
- ⏳ Optimization scripts updated
- ⏳ Downstream task evaluation complete

## Timeline

- **Week 1**: Evaluation and benchmarking
- **Week 2**: Update optimization scripts, ablation study
- **Week 3**: Downstream task evaluation
- **Week 4+**: Fine-tuning preparation (if evaluation shows promise)

