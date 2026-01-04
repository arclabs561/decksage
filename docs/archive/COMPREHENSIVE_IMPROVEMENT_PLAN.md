# Comprehensive Improvement Plan

Based on research and current state analysis, here's a systematic plan to improve embeddings, data, labeling, and training.

## Current State Analysis

### Embeddings
- **Current P@10**: 0.0278 (very weak)
- **Issues**:
  - Default hyperparameters (p=1.0, q=1.0, epochs=1)
  - No hyperparameter tuning
  - Single dimension (128)
  - No data preprocessing/enrichment
  - Limited training (1 epoch)

### Data
- **Issues**:
  - No graph enrichment (knowledge completion)
  - No multi-level embedding
  - Missing node attributes
  - No temporal information in graph
  - Limited co-occurrence filtering

### Labeling
- **Current**: 38 queries (94.7% coverage)
- **Issues**:
  - Small test set
  - No systematic expansion
  - Limited LLM-as-Judge usage
  - No iterative refinement
  - Missing diverse card types

### Training
- **Issues**:
  - No validation during training
  - No early stopping
  - No hyperparameter optimization
  - Single training run
  - No evaluation during training

## Improvement Strategy

### Phase 1: Embedding Improvements (Highest Impact)

#### 1.1 Hyperparameter Tuning
- **Research Finding**: p and q are critical, Node2Vec is robust but tuning helps
- **Action**: Create hyperparameter search script
- **Parameters to tune**:
  - p: [0.25, 0.5, 1.0, 2.0, 4.0]
  - q: [0.25, 0.5, 1.0, 2.0, 4.0]
  - walk_length: [40, 80, 120]
  - num_walks: [5, 10, 20]
  - dim: [64, 128, 256]
  - epochs: [1, 5, 10]

#### 1.2 Better Training
- **Research Finding**: More epochs help, proper evaluation during training
- **Action**:
  - Increase epochs (5-10)
  - Add validation split
  - Add early stopping
  - Track training metrics

#### 1.3 Data Preprocessing
- **Research Finding**: Knowledge completion and graph enrichment improve embeddings
- **Action**:
  - Add implicit relationships (knowledge completion)
  - Enrich with node attributes (card types, colors, mana costs)
  - Multi-level embedding framework
  - Better edge weighting

### Phase 2: Data Improvements

#### 2.1 Graph Enrichment
- Add card attributes as node features
- Temporal information (when cards were played together)
- Format/archetype metadata
- Price/rarity information

#### 2.2 Better Edge Construction
- Weighted edges based on co-occurrence frequency
- Temporal decay (recent co-occurrences weighted higher)
- Format-specific edges
- Archetype-specific edges

### Phase 3: Labeling Improvements

#### 3.1 Test Set Expansion
- **Target**: 100+ queries per game
- **Method**: LLM-as-Judge with iterative refinement
- **Strategy**:
  - Generate diverse queries (different card types, formats)
  - Use LLM-as-Judge with clear criteria
  - Human review for quality
  - Iterative refinement based on disagreements

#### 3.2 Better Annotation Quality
- **Research Finding**: Clear criteria, examples, iterative refinement
- **Action**:
  - Expand judge prompts with examples
  - Multi-judge consensus
  - Calibration against human experts
  - Adversarial test cases

### Phase 4: Training Improvements

#### 4.1 Proper Training Loop
- Validation split
- Early stopping
- Learning rate scheduling
- Regularization (dropout, weight decay)

#### 4.2 Evaluation During Training
- Track validation metrics
- Save best model
- Hyperparameter logging
- Training curves

## Implementation Priority

1. **Immediate** (Highest ROI):
   - Hyperparameter tuning for embeddings
   - Increase epochs and add validation
   - Test set expansion with LLM-as-Judge

2. **Short-term**:
   - Graph enrichment with attributes
   - Better training loop
   - Multi-judge consensus

3. **Medium-term**:
   - Knowledge completion preprocessing
   - Multi-level embedding
   - Temporal information

4. **Long-term**:
   - Advanced GNN architectures
   - Meta-learning approaches
   - Continuous learning

## Expected Impact

### Embeddings
- **Current**: P@10 = 0.0278
- **Target**: P@10 = 0.15-0.20 (5-7x improvement)
- **Methods**: Hyperparameter tuning, better training, data enrichment

### Overall System
- **Current**: Jaccard best (P@10 = 0.0833)
- **Target**: Fusion P@10 = 0.20-0.25 (meet README goal)
- **Methods**: Better embeddings + optimized fusion weights
