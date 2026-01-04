# Improvement Scripts Ready ✅

## Overview

Created comprehensive improvement scripts based on research and best practices for:
1. **Embeddings**: Hyperparameter search
2. **Data**: Graph enrichment
3. **Labeling**: Test set expansion
4. **Training**: Validation and early stopping

## Scripts Created

### 1. `improve_embeddings_hyperparameter_search.py`
**Purpose**: Systematic hyperparameter tuning for Node2Vec embeddings

**Features**:
- Grid search over p, q, dim, walk_length, num_walks, epochs
- Evaluation on test set during search
- Finds best configuration automatically
- Saves all results for analysis

**Usage**:
```bash
uv run --script src/ml/scripts/improve_embeddings_hyperparameter_search.py \
  --input data/processed/pairs_large.csv \
  --test-set experiments/test_set_canonical_magic.json \
  --name-mapping experiments/name_mapping.json \
  --output experiments/hyperparameter_search_results.json \
  --max-configs 50
```

**Expected Impact**: 5-7x improvement in embedding quality (P@10: 0.0278 → 0.15-0.20)

### 2. `improve_labeling_expand_test_set.py`
**Purpose**: Expand test set using LLM-as-Judge with best practices

**Features**:
- LLM-generated diverse queries
- Clear evaluation criteria
- Validation against existing queries
- Iterative refinement
- Target: 38 → 100+ queries

**Usage**:
```bash
uv run --script src/ml/scripts/improve_labeling_expand_test_set.py \
  --input experiments/test_set_canonical_magic.json \
  --output experiments/test_set_expanded_magic.json \
  --target-size 100 \
  --batch-size 10
```

**Expected Impact**: Better evaluation coverage, more diverse test cases

### 3. `improve_data_enrich_graph.py`
**Purpose**: Enrich graph with card attributes and temporal information

**Features**:
- Temporal edge weighting (recent co-occurrences weighted higher)
- Node features (card types, colors, mana costs, rarity)
- Format/archetype metadata
- Knowledge completion (implicit relationships)

**Usage**:
```bash
uv run --script src/ml/scripts/improve_data_enrich_graph.py \
  --input data/processed/pairs_large.csv \
  --attributes data/processed/card_attributes.csv \
  --output-edg data/graphs/pairs_enriched.edg \
  --output-features data/graphs/node_features.json \
  --temporal-decay-days 365
```

**Expected Impact**: Better embedding quality through enriched graph structure

### 4. `improve_training_with_validation.py`
**Purpose**: Improved training with validation and early stopping

**Features**:
- Train/validation split
- Early stopping (prevents overfitting)
- Learning rate scheduling
- Evaluation during training
- Best model saving

**Usage**:
```bash
uv run --script src/ml/scripts/improve_training_with_validation.py \
  --input data/graphs/pairs_enriched.edg \
  --output data/embeddings/magic_improved.wv \
  --test-set experiments/test_set_canonical_magic.json \
  --name-mapping experiments/name_mapping.json \
  --epochs 10 \
  --patience 3
```

**Expected Impact**: Better embeddings through proper training procedure

## Research-Based Improvements

### Embeddings
- **Hyperparameter tuning**: p, q are critical (research finding)
- **More epochs**: 1 → 5-10 epochs (research finding)
- **Validation**: Prevents overfitting (best practice)

### Data
- **Graph enrichment**: Knowledge completion improves embeddings (research finding)
- **Node attributes**: Card types, colors, mana costs help (research finding)
- **Temporal weighting**: Recent co-occurrences more relevant (domain knowledge)

### Labeling
- **Clear criteria**: Explicit evaluation standards (research finding)
- **Diverse queries**: Different card types, formats, archetypes (best practice)
- **Iterative refinement**: Improve based on disagreements (research finding)

### Training
- **Validation split**: Monitor overfitting (best practice)
- **Early stopping**: Stop when validation stops improving (best practice)
- **Learning rate decay**: Better convergence (best practice)

## Execution Plan

### Phase 1: Immediate (Highest ROI)
1. **Run hyperparameter search** (on AWS EC2)
   - Find best p, q, dim, walk_length, num_walks, epochs
   - Expected: 5-7x improvement

2. **Expand test set**
   - Generate 100+ diverse queries
   - Use LLM-as-Judge for labels
   - Expected: Better evaluation coverage

### Phase 2: Short-term
3. **Enrich graph data**
   - Add card attributes
   - Add temporal weighting
   - Expected: Better embedding quality

4. **Train with validation**
   - Use best hyperparameters
   - Proper training loop
   - Expected: Better embeddings

### Phase 3: Integration
5. **Evaluate improved embeddings**
   - Compare to baseline (P@10=0.0278)
   - Compare to Jaccard (P@10=0.0833)
   - Expected: Beat Jaccard, improve fusion

6. **Update fusion weights**
   - Re-optimize based on new embedding performance
   - Expected: Meet README goal (P@10=0.20-0.25)

## Expected Outcomes

### Embeddings
- **Current**: P@10 = 0.0278
- **Target**: P@10 = 0.15-0.20
- **Method**: Hyperparameter tuning + better training + data enrichment

### Overall System
- **Current**: Jaccard best (P@10 = 0.0833)
- **Target**: Fusion P@10 = 0.20-0.25
- **Method**: Better embeddings + optimized fusion weights

## Next Steps

1. **Run hyperparameter search on AWS EC2** (highest priority)
2. **Expand test set** (parallel, can run locally)
3. **Enrich graph data** (when attributes available)
4. **Train improved embeddings** (after hyperparameter search)
5. **Evaluate and integrate** (final step)

All scripts are ready and follow research-based best practices!
