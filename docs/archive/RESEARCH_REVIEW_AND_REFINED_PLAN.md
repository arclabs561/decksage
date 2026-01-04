# Research Review and Refined Implementation Plan

**Date**: November 10, 2025
**Context**: Deep research review, codebase analysis, and refined actionable plan

---

## Research Findings Summary

### Key Papers Identified

1. **"Learning With Generalised Card Representations for Magic: The Gathering"** (arXiv:2407.05879, 2024)
   - **Siamese networks** for card-deck fit (not just card similarity)
   - **55% accuracy** predicting human choices on unseen cards
   - Multi-modal: numerical, nominal, text, images, meta
   - **Critical insight**: Distance models card-deck fit, not just similarity

2. **"Can Learned Optimization Make Reinforcement Learning Less Difficult?"** (arXiv:2407.07082, 2025)
   - Meta-learning for RL (OPEN framework)
   - Efficient action space handling
   - Cross-environment generalization

3. **Action Space Research**:
   - **LASER**: Learning Latent Action Spaces (arXiv:2103.15793)
   - **FAR**: Factored Action Representations (arXiv:1705.07269)
   - Latent action frameworks for end-to-end agents

4. **Contextual Preference Ranking** (arXiv:2105.11864)
   - Contrastive learning for card-deck fit
   - Ranking loss (triplet, margin)
   - Context-dependent recommendations

---

## Codebase Review Findings

### Current Architecture

**API Structure** (FastAPI):
- Endpoints: `/v1/cards/{card_name}/similar`, `/v1/similar` (POST)
- Modes: `embedding`, `jaccard`, `synergy`, `fusion`
- Health: `/live`, `/ready`
- Uses Pydantic for validation

**Similarity Methods** (`src/ml/similarity/`):
- `similarity_methods.py`: Core similarity functions
- `card_similarity_pecan.py`: Node2Vec embeddings (PecanPy)
- **Missing**: `fusion.py` (fusion logic likely in similarity_methods.py)

**Deck Completion** (`src/ml/deck_building/`):
- `deck_completion.py`: Greedy completion algorithm
- `deck_patch.py`: Action space (add/remove/replace)
- `deck_env.py`: Gym-like environment (ready for RL!)
- `completion_eval.py`: Evaluation metrics

**Action Space**:
- ✅ Defined: `DeckPatch` with ops (add/remove/replace/move)
- ✅ Environment: `DeckCompletionEnv` with `step(action)` and `reward`
- ❌ Missing: RL agent implementation
- ❌ Missing: Reward function based on deck quality

**Dependencies**:
- FastAPI, uvicorn (HTTP service)
- PecanPy (Node2Vec embeddings)
- Pydantic, Pydantic-AI (validation, LLM)
- **Missing**: PyTorch, PyTorch Geometric, sentence-transformers

---

## Refined Implementation Plan

### Phase 0: Quick Wins & Exploration (This Week)
**Goal**: Get hands-on experience, validate approach

#### 0.1: Text Embeddings - Simple Implementation
**Why First**:
- Biggest expected impact (P@10: 0.08 → 0.15-0.18)
- No complex dependencies
- Can integrate immediately

**Implementation**:
```python
# New: src/ml/similarity/text_embeddings.py
# Simple sentence-transformers integration
# Cache embeddings to disk
# Add to fusion weights
```

**Effort**: 4-6 hours
**Validation**: Compare P@10 before/after on test set

#### 0.2: Review & Document API Endpoints
**Why**:
- Understand current HTTP service structure
- Identify integration points
- Document for future work

**Tasks**:
- Map all endpoints
- Document request/response formats
- Identify where to add new signals
- Test current performance

**Effort**: 2-3 hours

#### 0.3: Explore Fusion Implementation
**Why**:
- Need to understand current fusion logic
- Identify where to add text embeddings
- See current weight structure

**Tasks**:
- Find fusion code (likely in similarity_methods.py)
- Understand aggregators (weighted, RRF, CombSUM, CombMNZ)
- Review fusion_grid_search_latest.json structure

**Effort**: 1-2 hours

---

### Phase 1: Foundation Improvements (Weeks 1-2)
**Goal**: Add missing SOTA components with measurable impact

#### 1.1: Text Embeddings Integration ✅ (From Phase 0)
- Implement `CardTextEmbedder` class
- Add to fusion with 30-40% weight
- Re-run grid search for optimal weights
- **Expected**: P@10 = 0.15-0.18

#### 1.2: PyTorch Geometric Setup
**Dependencies**:
```bash
uv add torch torch-geometric sentence-transformers
```

**Implementation**:
- Build card-deck graph from co-occurrence pairs
- Simple GCN encoder (2 layers)
- Use GNN embeddings as additional signal
- **Expected**: +5-10% improvement

**Effort**: 10-15 hours

#### 1.3: Beam Search for Deck Completion
**Why**:
- Current greedy is suboptimal
- Beam search is simpler than full RL
- Multi-objective scoring (similarity + coverage + curve)

**Implementation**:
- Replace greedy in `deck_completion.py`
- Beam width: 3-5
- Multi-objective scoring function
- **Expected**: Better deck quality (measured via T0.2 metrics)

**Effort**: 6-10 hours

**Total Phase 1**: 20-31 hours
**Expected Outcome**: P@10 = 0.20-0.28 (meeting README goal)

---

### Phase 2: Advanced Methods (Weeks 3-4)
**Goal**: Match/exceed SOTA performance

#### 2.1: Siamese Network for Card-Deck Fit
**Architecture**:
- Two-tower: card encoder + deck encoder
- Contrastive loss (margin ranking)
- Train on tournament deck data

**Key Insight from Paper**:
- Distance = card-deck fit (lower = better)
- Not just card similarity, but contextual fit
- 55% accuracy on unseen cards

**Implementation**:
```python
# New: src/ml/similarity/siamese_network.py
# Card encoder: functional tags + text + stats
# Deck encoder: aggregate of card embeddings
# Loss: margin ranking (positive closer than negative)
```

**Effort**: 15-20 hours
**Expected**: P@10 = 0.30-0.35

#### 2.2: RL Agent (If Beam Search Insufficient)
**Environment**: Already exists! (`DeckCompletionEnv`)
- `reset(deck)`, `step(action)`, `observation()`, `reward`

**Agent Options**:
- **PPO**: Good for continuous action spaces
- **DQN**: Discrete actions (add card X, remove card Y)
- **A2C**: Simpler than PPO, good baseline

**Reward Function**:
- Deck quality metrics (from T0.2)
- Simulated win rate (if game simulator available)
- Functional coverage
- Mana curve fit

**Effort**: 20-30 hours
**Expected**: Long-term optimization vs greedy/beam

#### 2.3: Graph Neural Network Enhancement
**Beyond Simple GCN**:
- **GAT** (Graph Attention): Attention over neighbors
- **Message Passing**: Multi-hop card synergies
- **Hierarchical**: Card → Archetype → Format

**Effort**: 12-18 hours
**Expected**: Better synergy modeling

**Total Phase 2**: 47-68 hours
**Expected Outcome**: P@10 = 0.30-0.40 (approaching SOTA)

---

### Phase 3: Evaluation & Production (Week 5)
**Goal**: Rigorous validation

#### 3.1: Expanded Test Set (T0.1)
- 100+ queries (currently 38)
- Bootstrapped confidence intervals
- Cross-game validation

#### 3.2: Deck Quality Metrics (T0.2)
- Mana curve fit
- Tag balance (Shannon entropy)
- Synergy coherence
- Comparison to tournament decks

#### 3.3: A/B Testing Framework (T1.2)
- Compare: Greedy vs Beam vs RL
- Statistical significance
- Performance reports

**Total Phase 3**: 18-28 hours

---

## Immediate Next Steps (Today)

### 1. Explore Current Code (30 min)
```bash
# Find fusion implementation
grep -r "fusion\|Fusion" src/ml/

# Review API structure
grep -E "^def |@app\.|@router\." src/ml/api/api.py

# Check current similarity methods
head -100 src/ml/similarity/similarity_methods.py
```

### 2. Install Dependencies (5 min)
```bash
uv add sentence-transformers
# Test import
uv run python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

### 3. Implement Text Embeddings (2-3 hours)
- Create `src/ml/similarity/text_embeddings.py`
- Simple caching to disk
- Test on sample cards
- Measure embedding similarity vs current methods

### 4. Integrate into Fusion (1-2 hours)
- Find fusion code
- Add text_embed signal
- Update weights (start with 30% text, 70% existing)
- Test on API endpoint

### 5. Quick Validation (30 min)
- Run on test set
- Compare P@10 before/after
- Document results

**Total Today**: 4-6 hours
**Outcome**: Text embeddings working, integrated, measured

---

## Research Questions to Answer

### 1. Author/Researcher
- **Marcelo Prates**: Published on MTG neural networks
- **Question**: Current work? PyTorch Geometric usage?
- **Action**: Search for recent publications

### 2. GNN Architectures
- **Question**: GCN vs GAT vs GraphSAGE for card games?
- **Hypothesis**: GAT (attention) might capture synergies better
- **Action**: Start with GCN (simpler), upgrade to GAT if needed

### 3. Action Space Efficiency
- **Question**: How to handle large action spaces (thousands of cards)?
- **Papers**: LASER, FAR suggest factorization
- **Action**: Start with beam search (prunes naturally), consider RL later

### 4. Generalization to New Cards
- **Question**: How well does system work on newly released cards?
- **Paper Insight**: Siamese networks help (55% accuracy on unseen)
- **Action**: Test on recent card releases, measure performance

---

## Code Structure to Understand

### Current Fusion (Need to Find)
```python
# Likely in similarity_methods.py or separate fusion.py
# Should have:
# - Weighted fusion
# - RRF (Reciprocal Rank Fusion)
# - CombSUM, CombMNZ
# - Current weights from fusion_grid_search_latest.json
```

### API Integration Points
```python
# src/ml/api/api.py
# Endpoints:
# - GET /v1/cards/{card}/similar?mode=fusion
# - POST /v1/similar (with weights override)
#
# Need to:
# - Add text_embed to available signals
# - Update fusion to include text
# - Expose in API
```

### Deck Completion Flow
```python
# src/ml/deck_building/deck_completion.py
# Current: greedy (pick best card each step)
#
# Need to:
# - Add beam search option
# - Multi-objective scoring
# - Integration with text embeddings
```

---

## Success Metrics

### Phase 0 (This Week)
- [ ] Text embeddings implemented and tested
- [ ] API reviewed and documented
- [ ] Fusion code understood
- [ ] Baseline P@10 measured

### Phase 1 (Weeks 1-2)
- [ ] P@10 = 0.20-0.28 (meeting README goal)
- [ ] GNN encoder working
- [ ] Beam search implemented
- [ ] All integrated into API

### Phase 2 (Weeks 3-4)
- [ ] P@10 = 0.30-0.40 (approaching SOTA)
- [ ] Siamese network trained
- [ ] RL agent (if needed) working
- [ ] Full evaluation complete

---

## Risk Mitigation

### Risk 1: Text Embeddings Don't Help
**Mitigation**:
- Test on small sample first
- Compare to baseline before full integration
- Have fallback (keep current fusion)

### Risk 2: GNN Too Complex
**Mitigation**:
- Start with simple GCN (2 layers)
- Use pre-trained embeddings if available
- Can skip if text embeddings sufficient

### Risk 3: Beam Search Slower
**Mitigation**:
- Make it optional (config flag)
- Limit beam width (3-5)
- Cache candidate generation

### Risk 4: RL Training Difficult
**Mitigation**:
- Start with beam search first
- Only add RL if beam insufficient
- Use existing environment (already built!)

---

## Conclusion

**Refined Approach**:
1. **Start Small**: Text embeddings (biggest impact, simplest)
2. **Validate**: Measure improvements at each step
3. **Iterate**: Add GNN, beam search, then advanced methods
4. **Document**: Keep track of what works/doesn't

**Estimated Total Effort**: 85-127 hours
**Expected Final P@10**: 0.35-0.42 (matching/exceeding SOTA)

**Next Action**: Implement text embeddings today (4-6 hours)
