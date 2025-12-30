# Continue All Fronts - Strategic Plan

## Reasoning Through What's Best

### Current State
- ✅ Test set: 98 queries (target: 100+)
- ✅ Labels: 60 queries labeled with LLM-as-Judge
- ✅ Graph enrichment: Enriched edgelist and node features created
- ✅ Card attributes: Scryfall enrichment script ready (100/26,959 tested)
- 🔄 Hyperparameter search: Running on AWS EC2
- ✅ Multi-game training: Scripts created, ready to use

### Priority Assessment

#### 1. Embeddings (Highest Impact)
**Current**: P@10 = 0.0278 (very weak)  
**Target**: P@10 = 0.15-0.20 (5-7x improvement)

**Best Approach**:
- ✅ Hyperparameter search running (wait for results)
- ✅ Use trainctl for future training
- **Next**: Train improved embeddings with best hyperparameters using trainctl

#### 2. Data (High Impact)
**Current**: Basic co-occurrence graph  
**Target**: Enriched graph with attributes, temporal info

**Best Approach**:
- ✅ Graph enrichment script ready
- ✅ Node features created (26,959 cards)
- ✅ Scryfall enrichment tested (100 cards)
- **Next**: Scale Scryfall enrichment to all cards (background job)

#### 3. Labeling (Medium Impact)
**Current**: 98 queries, 60 labeled  
**Target**: 100+ queries, all labeled

**Best Approach**:
- ✅ Test set expansion script ready
- ✅ Label generation script ready
- **Next**: Continue expansion to 100+, generate remaining labels

#### 4. Training (High Impact)
**Current**: Basic training (1 epoch, no validation)  
**Target**: Proper training loop with validation

**Best Approach**:
- ✅ Improved training script ready
- **Next**: Use trainctl to run improved training with validation

#### 5. Multi-Game (Future Impact)
**Current**: MTG only  
**Target**: Unified multi-game embeddings

**Best Approach**:
- ✅ Multi-game export script ready
- ✅ Multi-game training script ready
- **Next**: Export multi-game graph, then train unified embeddings

## Execution Plan

### Immediate (Today)

1. **Integrate trainctl**
   - Test trainctl with local training
   - Update training scripts for trainctl compatibility
   - Create justfile recipes

2. **Continue Data Enrichment**
   - Scale Scryfall enrichment (background)
   - Monitor progress

3. **Complete Labeling**
   - Expand test set to 100+ queries
   - Generate remaining labels

### Short-term (This Week)

4. **Hyperparameter Results**
   - Check AWS hyperparameter search results
   - Train improved embeddings with best config using trainctl

5. **Improved Training**
   - Run improved training with validation using trainctl
   - Compare to baseline

6. **Multi-Game Export**
   - Export multi-game graph
   - Train unified embeddings using trainctl

### Medium-term (Next Week)

7. **Evaluation**
   - Evaluate all improvements
   - Update fusion weights
   - Measure overall system improvement

8. **Integration**
   - Integrate improved embeddings into API
   - Update documentation
   - Deploy improvements

## trainctl Integration Tasks

### Task 1: Test trainctl Locally
```bash
# Test with simple training script
trainctl local src/ml/scripts/improve_training_with_validation.py \
    --input data/graphs/pairs_enriched.edg \
    --output data/embeddings/test_improved.wv
```

### Task 2: Update Training Scripts
- Add checkpoint support
- Ensure S3 paths work with trainctl
- Add progress logging for monitoring

### Task 3: Create justfile Recipes
```justfile
# Training recipes using trainctl
train-hyperparam:
    trainctl aws train {{instance}} src/ml/scripts/improve_embeddings_hyperparameter_search.py

train-improved:
    trainctl aws train {{instance}} src/ml/scripts/improve_training_with_validation.py

train-multigame:
    trainctl aws train {{instance}} src/ml/scripts/train_multi_game_embeddings.py
```

## Parallel Execution Strategy

### Can Run in Parallel
1. **Scryfall enrichment** (background, long-running)
2. **Test set expansion** (local, quick)
3. **Label generation** (local, uses LLM)
4. **Multi-game graph export** (local, one-time)

### Sequential (Dependencies)
1. **Hyperparameter search** → **Train improved embeddings** (needs results)
2. **Multi-game export** → **Multi-game training** (needs graph)
3. **All training** → **Evaluation** (needs models)

## Success Metrics

### Embeddings
- P@10: 0.0278 → 0.15-0.20 (5-7x improvement)

### Data
- 26,959 cards with attributes (from Scryfall)
- Enriched graph with temporal info
- Multi-game graph exported

### Labeling
- 100+ queries in test set
- All queries labeled

### Training
- Validation and early stopping working
- Checkpoint management via trainctl
- Training metrics tracked

### Multi-Game
- Multi-game graph exported
- Unified embeddings trained
- Game-specific embeddings trained

## Next Actions

1. ✅ Create trainctl integration plan
2. ⏳ Test trainctl locally
3. ⏳ Update training scripts for trainctl
4. ⏳ Continue data enrichment (background)
5. ⏳ Complete labeling (local)
6. ⏳ Check hyperparameter search results
7. ⏳ Train improved embeddings with trainctl
8. ⏳ Export multi-game graph
9. ⏳ Train multi-game embeddings with trainctl

**All fronts proceeding with trainctl integration!**

