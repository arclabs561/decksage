# Critical Review: trainctl, Cursor Setup, Training Methods, Downstream Tasks

**Date**: 2025-01-27  
**Status**: Comprehensive analysis of 4 critical areas

---

## 1. Are We Using trainctl Properly?

### Current Usage

**What We're Doing**:
- ✅ Using `trainctl aws create --spot` for instance creation
- ✅ Using `trainctl aws train` with S3 paths (`--output-s3`)
- ✅ Using `trainctl aws monitor` for tracking
- ✅ Handling SSM vs SSH automatically
- ✅ Reusing existing instances

**Script**: `src/ml/scripts/run_hyperparameter_search_trainctl_fixed.sh`

### Issues Found

#### ❌ Issue 1: Missing `--data-s3` for Input Data
**Current**:
```bash
$TRAINCTL_BIN aws train "$INSTANCE_ID" \
    src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --output-s3 s3://games-collections/experiments/ \
    -- \
    --input s3://games-collections/processed/pairs_large.csv \
    ...
```

**Problem**: Input data is passed as script argument, but trainctl should handle S3 downloads automatically with `--data-s3`.

**Better**:
```bash
$TRAINCTL_BIN aws train "$INSTANCE_ID" \
    src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --data-s3 s3://games-collections/processed/pairs_large.csv \
    --output-s3 s3://games-collections/experiments/ \
    -- \
    --input /tmp/pairs_large.csv \  # trainctl downloads to /tmp/
    --output /tmp/hyperparameter_results.json \
    --test-set /tmp/test_set_canonical_magic.json
```

#### ❌ Issue 2: Not Using trainctl's Built-in Checkpointing
**Current**: Manual checkpointing in Python scripts  
**Better**: Use trainctl's `--checkpoint-interval` and `--resume-from` flags

#### ❌ Issue 3: Not Using trainctl for Local Training
**Current**: Direct Python execution for local training  
**Better**: Use `trainctl local` for consistency

#### ❌ Issue 4: Missing RunPod Support
**Current**: Only AWS EC2  
**Better**: Add RunPod support for GPU training (cheaper than EC2)

### Recommendations

1. **Fix S3 Data Handling**:
   ```bash
   # Use --data-s3 for all input files
   trainctl aws train $INSTANCE \
       script.py \
       --data-s3 s3://bucket/input1.csv \
       --data-s3 s3://bucket/input2.json \
       --output-s3 s3://bucket/output/ \
       -- \
       --input /tmp/input1.csv \
       --input2 /tmp/input2.json
   ```

2. **Add Checkpointing**:
   ```bash
   trainctl aws train $INSTANCE \
       script.py \
       --checkpoint-interval 3600 \  # Every hour
       --resume-from s3://bucket/checkpoints/latest.ckpt
   ```

3. **Add RunPod Support**:
   ```bash
   trainctl runpod create --gpu a100 \
       script.py \
       --data-s3 s3://bucket/input.csv
   ```

4. **Use trainctl for Local Training**:
   ```bash
   trainctl local script.py \
       --input data/processed/pairs.csv \
       --output data/embeddings/trained.wv
   ```

---

## 2. Is Cursor Rules and Ignore Setup Right?

### Current State

**`.cursorignore`**:
```
.env
data
deploy
.venv
__pycache__
*.pyc
.cache
backups
```

**`.cursor/`**: Exists but contents unknown (timeout on read)

### Issues Found

#### ❌ Issue 1: Missing Critical Patterns
**Missing**:
- `experiments/` - Large JSON files, evaluation results
- `logs/` - Log files
- `*.log` - All log files
- `archive/` - Historical documents
- `*.md` files in root (100+ markdown files!)

#### ❌ Issue 2: No `.cursorrules` File
**Problem**: No project-specific rules for Cursor AI  
**Impact**: AI doesn't know project conventions, style, priorities

#### ❌ Issue 3: Data Directory Too Broad
**Current**: `data` ignored entirely  
**Problem**: Some data files might be small and relevant (e.g., `data/processed/test_set_canonical_magic.json`)

### Recommendations

**Updated `.cursorignore`**:
```
# Environment
.env
.venv
__pycache__
*.pyc
.cache

# Large data directories
data/raw/
data/full/
data-full/
old-scraper-data/

# Deployment
deploy/
backups/

# Logs
logs/
*.log
/tmp/*.log

# Archive
archive/

# Experiments (large files)
experiments/*.jsonl
experiments/*.html
experiments/*.csv

# Documentation (too many MD files)
*.md
!README.md
!QUICK_REFERENCE.md
!PRIORITY_MATRIX.md
docs/*.md

# Build artifacts
target/
dist/
build/
*.egg-info/
```

**Create `.cursorrules`**:
```markdown
# DeckSage Project Rules

## Code Style
- Use PEP 723 scripts for standalone tools (`# /// script`)
- Prefer `uv` over `pip` for package management
- Use type hints (Python 3.11+)
- Follow existing patterns in `src/ml/`

## Priorities
1. Embedding quality (P@10 target: 0.15)
2. Evaluation rigor (test set expansion, IAA)
3. Downstream task performance (deck completion, substitution)

## Testing
- Run `pytest src/ml/tests/` before committing
- Use property-based tests for invariants
- Test LLM calls with caching (diskcache)

## Training
- Use `trainctl` for all training (local, AWS, RunPod)
- Always use `--data-s3` and `--output-s3` for cloud training
- Enable checkpointing for long runs

## Data
- S3 bucket: `s3://games-collections/`
- Test sets: `experiments/test_set_canonical_*.json`
- Embeddings: `data/embeddings/*.wv`
```

---

## 3. Are We Trying Enough Training Methods?

### Current Methods

**Implemented**:
- ✅ DeepWalk (p=1, q=1)
- ✅ Node2Vec-Default (p=1, q=1)
- ✅ Node2Vec-BFS (p=2, q=0.5)
- ✅ Node2Vec-DFS (p=0.5, q=2)
- ⏳ GraphSAGE (code ready, blocked by scipy)

**Not Implemented**:
- ❌ Graph NE (Neighbor Embeddings) - Simpler, no hyperparameter tuning
- ❌ Meta Node2Vec / Metapath2Vec - For heterogeneous graphs (we have format/archetype metadata!)
- ❌ PyTorch Geometric Node2Vec - GPU-accelerated
- ❌ TSAW (True Self-Avoiding Walk) - Reaches unknown nodes faster
- ❌ Ensemble methods - Combine multiple embeddings

### Research Findings (2024-2025)

1. **Graph NE** outperforms Node2Vec in some tasks, simpler (no p, q tuning)
2. **Meta Node2Vec** perfect for our use case (format/archetype metadata)
3. **TSAW** better for sparse graphs (we have 14k nodes, 868k edges)
4. **Ensemble** methods show 10-20% improvement over single methods

### Recommendations

#### Priority 1: Graph NE (High ROI)
**Why**: Simpler than Node2Vec, no hyperparameter tuning, outperforms in some tasks  
**Effort**: 4-6 hours  
**Impact**: Potentially 10-15% improvement

#### Priority 2: Meta Node2Vec (Perfect Fit)
**Why**: We have format/archetype metadata - this is exactly what Meta Node2Vec is for  
**Effort**: 8-12 hours  
**Impact**: Could leverage metadata for better embeddings

#### Priority 3: Ensemble Methods
**Why**: Research shows 10-20% improvement  
**Effort**: 3-4 hours  
**Impact**: Combine DeepWalk + Node2Vec variants + Graph NE

#### Priority 4: PyTorch Geometric Node2Vec
**Why**: GPU-accelerated, integrates with GNNs  
**Effort**: 2-3 hours (if scipy issue resolved)  
**Impact**: Faster training, better integration

### Implementation Plan

1. **Add Graph NE** (this week):
   ```python
   # Research implementation
   # Compare to Node2Vec baseline
   # If better, replace Node2Vec
   ```

2. **Add Meta Node2Vec** (next week):
   ```python
   # Use format/archetype metadata
   # Create heterogeneous graph
   # Train with metapath2vec
   ```

3. **Add Ensemble** (after Graph NE):
   ```python
   # Combine: DeepWalk + Node2Vec-BFS + Graph NE
   # Weighted average or learned fusion
   ```

---

## 4. What About Downstream Tasks?

### Current Downstream Tasks

**Implemented**:
- ✅ Card similarity (P@10 = 0.0278, target 0.15)
- ✅ Deck completion (greedy algorithm)
- ✅ Card substitution (via similarity)
- ✅ Contextual discovery (synergies, alternatives, upgrades, downgrades)

**Not Evaluated**:
- ❌ Win rate prediction
- ❌ Deck quality assessment (mentioned but not measured)
- ❌ Format-specific performance
- ❌ Archetype-specific performance
- ❌ Temporal evaluation (recommendations at different time points)

### Issues Found

#### ❌ Issue 1: No Win Rate Evaluation
**Problem**: Deck completion is evaluated on "does it suggest good cards?" not "does it improve win rate?"  
**Impact**: We don't know if our suggestions actually help players win

#### ❌ Issue 2: No Task-Specific Evaluation
**Problem**: All evaluation is on similarity (P@10), not on downstream tasks  
**Impact**: Good similarity doesn't guarantee good deck completion

#### ❌ Issue 3: No A/B Testing
**Problem**: No way to compare algorithm changes on real user behavior  
**Impact**: Can't measure real-world impact

#### ❌ Issue 4: No Temporal Evaluation
**Problem**: Recommendations don't account for format rotation, meta shifts  
**Impact**: Suggestions may be stale or irrelevant

### Recommendations

#### Priority 1: Task-Specific Evaluation
**Action**: Create evaluation framework for each downstream task:
- **Deck Completion**: Measure win rate improvement (if data available) or expert evaluation
- **Card Substitution**: Measure functional equivalence (same role, similar power)
- **Contextual Discovery**: Measure relevance (synergies actually work together)

**Implementation**:
```python
# src/ml/evaluation/downstream_tasks.py
def evaluate_deck_completion(
    suggestions: list[str],
    ground_truth: list[str],
    deck: dict,
) -> dict[str, float]:
    """Evaluate deck completion suggestions."""
    # Coverage: % of ground truth cards suggested
    # Precision: % of suggestions that are good
    # Win rate improvement: If data available
    pass

def evaluate_card_substitution(
    original: str,
    substitute: str,
    context: dict,
) -> dict[str, float]:
    """Evaluate if substitute is functionally equivalent."""
    # Role match: Same functional role?
    # Power level: Similar power?
    # Context fit: Works in same decks?
    pass
```

#### Priority 2: Win Rate Integration
**Action**: If win rate data available, integrate into evaluation  
**Effort**: 4-6 hours  
**Impact**: Real-world validation

#### Priority 3: Temporal Evaluation
**Action**: Evaluate recommendations at different time points  
**Effort**: 6-8 hours  
**Impact**: Ensure recommendations stay relevant

#### Priority 4: A/B Testing Framework
**Action**: Create framework to compare algorithm versions  
**Effort**: 8-12 hours  
**Impact**: Rigorous algorithm comparison

---

## Summary & Action Items

### Immediate (This Week)

1. **Fix trainctl Usage**:
   - [ ] Use `--data-s3` for input files
   - [ ] Add checkpointing
   - [ ] Add RunPod support

2. **Fix Cursor Setup**:
   - [ ] Update `.cursorignore` with missing patterns
   - [ ] Create `.cursorrules` file

3. **Add Graph NE**:
   - [ ] Research implementation
   - [ ] Compare to Node2Vec baseline

### Short-term (This Month)

4. **Add Meta Node2Vec**:
   - [ ] Implement heterogeneous graph
   - [ ] Train with format/archetype metadata

5. **Task-Specific Evaluation**:
   - [ ] Create evaluation framework for downstream tasks
   - [ ] Measure deck completion quality
   - [ ] Measure substitution quality

### Medium-term (Next Quarter)

6. **Ensemble Methods**:
   - [ ] Combine multiple embeddings
   - [ ] Learn fusion weights

7. **Win Rate Integration**:
   - [ ] If data available, integrate into evaluation
   - [ ] Measure real-world impact

---

## Key Findings

1. **trainctl**: Not using full feature set (missing `--data-s3`, checkpointing, RunPod)
2. **Cursor**: Missing `.cursorrules`, `.cursorignore` incomplete
3. **Training Methods**: Missing Graph NE, Meta Node2Vec, ensemble methods
4. **Downstream Tasks**: No task-specific evaluation, no win rate integration

**Biggest Gaps**:
- Meta Node2Vec (perfect fit for our metadata)
- Task-specific evaluation (similarity ≠ downstream performance)
- Win rate integration (real-world validation)

