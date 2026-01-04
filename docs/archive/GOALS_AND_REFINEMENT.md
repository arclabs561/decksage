# Project Goals: Review and Refinement

## Current Goals (As Stated)

### Primary Objectives
1. **Card Similarity**: Find similar cards for a given card
2. **Deck Completion**: Suggest additions to incomplete decks
3. **Multi-modal Enrichment**: Combine various signals (co-occurrence, embeddings, functional tags, etc.)

### Current Performance
- **Embedding P@10**: 0.0278 (very weak)
- **Jaccard P@10**: 0.0833 (3x better than embedding)
- **Fusion P@10**: Expected lower than Jaccard alone (needs optimization)

## Refined Goals (Critical Analysis)

### 1. Card Similarity - Core Goal

**Current State**:
- Multiple signals available but poorly integrated
- Embedding quality is the bottleneck
- Evaluation shows Jaccard outperforms embeddings

**Refined Goal**:
- **Primary**: Achieve P@10 ≥ 0.15 for card similarity (5x improvement from current)
- **Secondary**: Achieve MRR ≥ 0.25 (meaningful ranking quality)
- **Tertiary**: Support multiple similarity modes (functional, archetype, format-specific)

**Success Criteria**:
- ✅ P@10 ≥ 0.15 on test set
- ✅ MRR ≥ 0.25
- ✅ Fusion outperforms individual signals
- ✅ Consistent performance across card types (creatures, spells, lands)

### 2. Deck Completion - Core Goal

**Current State**:
- Basic greedy algorithm
- Considers legality and budget
- Functional coverage awareness

**Refined Goal**:
- **Primary**: Suggest cards that improve deck win rate (requires win rate data)
- **Secondary**: Suggest cards that maintain/improve deck synergy
- **Tertiary**: Suggest cards that fit budget and format constraints

**Success Criteria**:
- ✅ Suggested cards are actually playable in the deck
- ✅ Suggested cards improve deck quality (measured by win rate or expert evaluation)
- ✅ Suggestions respect budget and format constraints
- ✅ Explanations for why cards are suggested

### 3. Multi-Modal Fusion - Enabling Goal

**Current State**:
- Multiple signals available (embedding, Jaccard, functional, text, sideboard, temporal, GNN, archetype, format)
- Fusion weights not optimized
- Some signals not yet computed

**Refined Goal**:
- **Primary**: Optimize fusion weights to maximize P@10
- **Secondary**: Compute all available signals
- **Tertiary**: Learn signal importance per query type

**Success Criteria**:
- ✅ Fusion outperforms best individual signal
- ✅ All available signals are computed and integrated
- ✅ Signal weights are data-driven (not hand-tuned)

### 4. Evaluation Framework - Enabling Goal

**Current State**:
- Test set: 100 queries (target reached)
- Labels: 38/100 queries labeled
- Evaluation metrics: P@10, MRR

**Refined Goal**:
- **Primary**: Complete labeling for all 100 queries
- **Secondary**: Expand test set to 200+ queries for robustness
- **Tertiary**: Add temporal evaluation (recommendations at different time points)

**Success Criteria**:
- ✅ 200+ queries in test set
- ✅ All queries have high-quality labels
- ✅ Temporal evaluation framework in place
- ✅ Inter-annotator agreement metrics tracked

### 5. Data Quality - Enabling Goal

**Current State**:
- Graph enrichment: Complete
- Card attributes: 4.3% enriched (1,150/26,959)
- Multi-game graph: Incomplete export

**Refined Goal**:
- **Primary**: Enrich all 26,959 cards with attributes
- **Secondary**: Complete multi-game graph export
- **Tertiary**: Add temporal edge weights and format metadata

**Success Criteria**:
- ✅ 100% card attribute enrichment
- ✅ Multi-game graph exported
- ✅ Temporal and format metadata integrated

### 6. Training Infrastructure - Enabling Goal

**Current State**:
- Basic training (1 epoch, no validation)
- Hyperparameter search running
- trainctl integration in progress

**Refined Goal**:
- **Primary**: Use trainctl for all training operations
- **Secondary**: Implement validation and early stopping
- **Tertiary**: Add checkpoint management and resume capability

**Success Criteria**:
- ✅ All training uses trainctl
- ✅ Validation split and early stopping working
- ✅ Checkpoint management functional

## Prioritized Goal Hierarchy

### Tier 1: Critical Path (Blocking)
1. **Improve Embedding Quality** (P@10: 0.0278 → 0.15)
   - Hyperparameter search → Train with best config
   - This is the biggest bottleneck

2. **Complete Labeling** (38/100 → 100/100)
   - Needed for reliable evaluation
   - Currently blocking proper assessment

3. **Optimize Fusion Weights**
   - Once embeddings improve, fusion should outperform individual signals

### Tier 2: High Impact (Enabling)
4. **Complete Card Enrichment** (4.3% → 100%)
   - Enables better embeddings (node features)
   - Enables GNN training

5. **Complete Multi-Game Export**
   - Enables multi-game training
   - Larger training corpus

6. **Implement Validation in Training**
   - Prevents overfitting
   - Better model selection

### Tier 3: Future Enhancements
7. **Expand Test Set** (100 → 200+)
   - More robust evaluation
   - Better generalization assessment

8. **Temporal Evaluation**
   - Real-world relevance
   - Format rotation awareness

9. **Win Rate Integration**
   - Deck completion quality metric
   - Real-world validation

## Refined Success Metrics

### Short-term (This Week)
- ✅ Embedding P@10 ≥ 0.10 (4x improvement)
- ✅ All 100 queries labeled
- ✅ Fusion outperforms Jaccard alone
- ✅ Card enrichment ≥ 50%

### Medium-term (This Month)
- ✅ Embedding P@10 ≥ 0.15 (5x improvement)
- ✅ Test set expanded to 200+ queries
- ✅ Card enrichment 100%
- ✅ Multi-game embeddings trained
- ✅ Validation and early stopping working

### Long-term (Next Quarter)
- ✅ Embedding P@10 ≥ 0.20 (7x improvement)
- ✅ Deck completion improves win rates
- ✅ Temporal evaluation framework
- ✅ Production-ready API with all features

## Goal Alignment Check

**Are our goals aligned with user needs?**
- ✅ Card similarity: Core use case
- ✅ Deck completion: Core use case
- ✅ Multi-game support: Expands market
- ✅ Evaluation rigor: Ensures quality

**Are our goals achievable?**
- ✅ Embedding improvement: Yes (hyperparameter tuning + better training)
- ✅ Labeling completion: Yes (optimized script running)
- ✅ Card enrichment: Yes (rate-limited but doable)
- ✅ Fusion optimization: Yes (grid search)

**Are our goals measurable?**
- ✅ All goals have clear metrics (P@10, MRR, completion %)
- ✅ Evaluation framework in place
- ✅ Test set available

## Recommendations

1. **Focus on embedding quality first** - Biggest impact
2. **Complete labeling** - Needed for evaluation
3. **Optimize fusion** - Once embeddings improve
4. **Continue data enrichment** - Background task
5. **Complete multi-game export** - Enables future work

**Goals are well-defined and achievable. Focus on Tier 1 goals first.**
