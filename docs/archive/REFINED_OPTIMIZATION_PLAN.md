# Refined Optimization Plan

## Based on Goals Review and Research

### Priority 1: Embedding Quality (Critical Path)

**Current**: P@10 = 0.0278 (very weak)  
**Target**: P@10 ≥ 0.15 (5x improvement)

**Actions**:
1. ✅ Hyperparameter search running
2. ⏳ Wait for results, then train with best config
3. ⏳ Add validation split (80/20)
4. ⏳ Implement early stopping (patience=3)
5. ⏳ Add learning rate scheduling (reduce on plateau)

**Expected Impact**: 5-7x improvement in embedding quality

### Priority 2: Complete Labeling (Blocking Evaluation)

**Current**: 38/100 queries labeled  
**Target**: 100/100 queries labeled

**Actions**:
1. ✅ Optimized script running
2. ⏳ Monitor progress
3. ⏳ Verify label quality
4. ⏳ Add inter-annotator agreement tracking

**Expected Impact**: Reliable evaluation, can measure improvements

### Priority 3: Fusion Optimization (After Embeddings Improve)

**Current**: Fusion weights not optimized  
**Target**: Fusion outperforms best individual signal

**Actions**:
1. ⏳ Evaluate individual signal quality
2. ⏳ Grid search for optimal weights
3. ⏳ Consider query-dependent weights
4. ⏳ Add MMR for diversity

**Expected Impact**: 10-20% improvement over best single signal

### Priority 4: Data Quality (Enabling Future Work)

**Current**: 4.3% card enrichment, multi-game export incomplete  
**Target**: 100% enrichment, complete multi-game graph

**Actions**:
1. ✅ Optimized enrichment script running
2. ⏳ Monitor progress (background task)
3. ⏳ Complete multi-game export
4. ⏳ Add temporal edge weights

**Expected Impact**: Better embeddings (node features), multi-game training

### Priority 5: Training Infrastructure (Enabling Quality)

**Current**: Basic training, no validation  
**Target**: Validation, early stopping, checkpointing

**Actions**:
1. ⏳ Integrate trainctl
2. ⏳ Add validation split to training
3. ⏳ Implement early stopping
4. ⏳ Add checkpoint management

**Expected Impact**: Better model selection, prevent overfitting

## Implementation Order

### Week 1: Critical Path
1. Complete labeling (62 queries)
2. Get hyperparameter results
3. Train improved embeddings with best config
4. Evaluate improvements

### Week 2: Optimization
1. Optimize fusion weights
2. Add validation to training
3. Continue card enrichment
4. Complete multi-game export

### Week 3: Integration
1. Train multi-game embeddings
2. Integrate all improvements into API
3. Evaluate overall system
4. Deploy improvements

## Success Metrics

### Short-term (This Week)
- ✅ Embedding P@10 ≥ 0.10
- ✅ All 100 queries labeled
- ✅ Fusion outperforms Jaccard

### Medium-term (This Month)
- ✅ Embedding P@10 ≥ 0.15
- ✅ Card enrichment ≥ 50%
- ✅ Validation and early stopping working

### Long-term (Next Quarter)
- ✅ Embedding P@10 ≥ 0.20
- ✅ Multi-game embeddings trained
- ✅ Production-ready system

## Research-Based Optimizations

### From Research:
1. **Node2Vec**: p=1.0, q=1.0 good starting point
2. **Walk length**: 2 * average_path_length
3. **Fusion**: RRF robust default, grid search for weights
4. **Evaluation**: Multiple judges, calibration, agreement metrics

### To Apply:
1. Use research-backed hyperparameter ranges
2. Implement validation and early stopping
3. Optimize fusion with grid search
4. Complete labeling with quality checks

**Plan is research-backed and executable. Focus on Priority 1 first.**

