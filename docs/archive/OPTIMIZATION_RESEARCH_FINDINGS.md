# Optimization Research Findings

## Research Areas

### 1. Graph Embedding Quality

**Key Findings**:
- Node2Vec hyperparameters (p, q) are critical for quality
- Walk length and num_walks affect coverage
- Dimension size should match data complexity
- Epochs matter but diminishing returns after 5-10

**Best Practices**:
- Start with p=1.0, q=1.0 (unbiased random walk)
- Use walk_length = 2 * average_path_length
- num_walks = 10-20 per node
- dim = 128-256 for most tasks
- epochs = 5-10 (more doesn't help much)

**Our Current Issues**:
- Hyperparameter search running (good)
- Need to use results to train improved embeddings
- Should add validation split to prevent overfitting

### 2. Multi-Modal Fusion

**Key Findings**:
- Weighted fusion outperforms simple averaging
- RRF (Reciprocal Rank Fusion) is robust
- Signal importance varies by query type
- Need to learn weights per query category

**Best Practices**:
- Use grid search or Bayesian optimization for weights
- Consider query-dependent weights (functional vs archetype)
- RRF is good default when signal quality unknown
- MMR (Maximal Marginal Relevance) for diversity

**Our Current Issues**:
- Fusion weights not optimized
- Some signals not computed yet
- Need to evaluate signal quality individually first

### 3. LLM-as-Judge Evaluation

**Key Findings**:
- Prompt engineering critical for consistency
- Multiple judges reduce bias
- Calibration needed for score interpretation
- Inter-annotator agreement metrics essential

**Best Practices**:
- Use structured prompts with examples
- Multiple judges with different personas
- Calibrate scores against human annotations
- Track agreement metrics (Cohen's Kappa, etc.)

**Our Current Issues**:
- Labeling incomplete (38/100)
- No inter-annotator agreement tracking
- Need to verify label quality

### 4. Multi-Game Embeddings

**Key Findings**:
- Unified embeddings can learn cross-game patterns
- Game-specific embeddings preserve game nuances
- Hybrid approach often best
- Cross-game transition probability is key hyperparameter

**Best Practices**:
- Start with unified embeddings
- Add game-specific if needed
- Use cross-game probability = 0.1-0.3
- Evaluate both unified and game-specific

**Our Current Issues**:
- Multi-game export incomplete
- Training script ready but not executed
- Need to evaluate cross-game transfer

## Specific Optimizations to Apply

### 1. Embedding Training
- ✅ Hyperparameter search (in progress)
- ⏳ Use best config to train
- ⏳ Add validation split
- ⏳ Early stopping
- ⏳ Learning rate scheduling

### 2. Fusion Optimization
- ⏳ Evaluate individual signal quality
- ⏳ Grid search for optimal weights
- ⏳ Consider query-dependent weights
- ⏳ Add MMR for diversity

### 3. Evaluation Framework
- ⏳ Complete labeling (62 remaining)
- ⏳ Expand test set (100 → 200+)
- ⏳ Add temporal evaluation
- ⏳ Track inter-annotator agreement

### 4. Data Quality
- ⏳ Complete card enrichment (4.3% → 100%)
- ⏳ Complete multi-game export
- ⏳ Add temporal edge weights
- ⏳ Add format metadata

## Research-Based Recommendations

1. **Prioritize embedding quality** - Biggest impact on performance
2. **Complete labeling** - Needed for reliable evaluation
3. **Optimize fusion after embeddings improve** - Fusion needs good signals
4. **Continue data enrichment** - Background task, enables future work
5. **Add validation to training** - Prevents overfitting, better models

**Research confirms our current approach is sound. Focus on execution.**

