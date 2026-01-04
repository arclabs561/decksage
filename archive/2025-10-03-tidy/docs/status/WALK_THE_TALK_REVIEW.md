# Walk the Talk Review - October 2, 2025

Checking if the repository practices match the stated principles.

## Stated Principles (from README)

1. **Experience complexity before abstracting**
2. **Significant critique over premature optimization**
3. **Honest assessment over inflated claims**
4. **Data quality over algorithmic sophistication**
5. **Tests for regression prevention**

---

## Analysis: Do We Walk the Talk?

### ✅ What's Aligned

**1. Honest Assessment** ✅
- README is truthful about capabilities
- Documents what's working vs in-progress
- Findings.md shows genuine evaluation (Jaccard beats Node2Vec)
- No inflated claims

**2. Data Quality Focus** ✅
- Architecture review explicitly discusses data issues
- Multiple experiments on data cleaning (land filtering)
- Prioritized fixing bugs over adding features
- 57 Go tests for data extraction

**3. Backend Engineering** ✅
- Go code follows good practices
- Proper abstractions (game interface, dataset interface)
- Tests for regression (57 tests)
- Clean separation of concerns

### ❌ What's Misaligned

**1. "Experience before abstracting" - VIOLATED** ❌

**Evidence:**
- 19 experiment scripts (`run_exp_*.py`) totaling 2,685 lines
- LANDS constant duplicated in 11+ files
- Path loading duplicated across files:
  - `../backend/pairs_large.csv` (7 times)
  - `../../data/embeddings/` (multiple times)
  - Inconsistent paths between scripts
- Similar evaluation loops copy-pasted
- No `utils.py` or `constants.py`

**Reality Check:**
We've clearly **experienced enough complexity** to warrant abstraction. After 19 experiments, we know the patterns:
- Load graph data
- Filter lands
- Compute similarity
- Evaluate on test set
- Log results

**Should do:**
```python
# utils/constants.py
BASIC_LANDS = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}

# utils/data_loading.py
def load_pairs(dataset='large'):
    """Load pairs from canonical location"""

def load_embeddings(name):
    """Load embeddings from canonical location"""

# utils/evaluation.py
def evaluate_similarity(test_set, sim_func, top_k=10):
    """Standard evaluation loop"""
```

**2. "Tests for regression prevention" - VIOLATED** ❌

**Go Backend:**
- ✅ 57 tests, all passing
- ✅ Covers critical paths (data extraction, parsing)
- ✅ Test data in testdata/

**Python ML:**
- ❌ 1 test file (`test_llm_judge.py`)
- ❌ No tests for evaluation metrics
- ❌ No tests for data loading
- ❌ No tests for similarity functions
- ❌ 49 Python files, ~10K lines, minimal testing

**Critical Gap:**
The system that generates all results (ML pipeline) has almost no automated tests. We're testing the plumbing (Go) but not the science (Python).

**Should have:**
- `test_evaluate.py` - Verify metrics calculations
- `test_similarity.py` - Test Jaccard, cosine, etc
- `test_data_loading.py` - Ensure consistent paths
- `test_experiment_logging.py` - Verify JSONL format

**3. Duplicate Experiment Logs** ❌

**In `experiments/`:**
- `EXPERIMENT_LOG.jsonl` (6 lines) - simplified
- `EXPERIMENT_LOG_EVOLVED.jsonl` (35 lines) - full
- `EXPERIMENT_LOG_BACKUP.jsonl` (36 lines) - backup
- `experiments.jsonl` (different format!)

**In `src/ml/`:**
- `experiments.jsonl` (different from above)

**Reality:** Multiple sources of truth violates principle of honest/clear systems.

**4. Inconsistent Evaluation** ⚠️

Different experiments use different:
- Test set paths (canonical vs v1 vs weighted)
- Evaluation metrics (some P@10, some custom weights)
- Land filtering (some filter, some don't)
- Data paths (backend/ vs data/processed/)

This makes cross-experiment comparison difficult.

---

## Concrete Issues

### Code Duplication
```python
# Appears in 11+ files:
LANDS = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}

# Appears in 7+ files:
df = pd.read_csv('../backend/pairs_large.csv')

# Similar loops in every experiment:
for query, labels in test_set.items():
    # ... compute similarity ...
    # ... score results ...
    scores.append(score / 10.0)
```

### Path Inconsistency
```python
# Different files use different paths:
'../backend/pairs_large.csv'
'../backend/pairs_500decks.csv'
'../../data/processed/pairs_large.csv'
'../../data/embeddings/magic_39k_decks_pecanpy.wv'
'../../data/embeddings/node2vec_default.wv'
```

### No Shared Framework
Each experiment reimplements:
- Graph adjacency building
- Land filtering
- Jaccard calculation
- Evaluation scoring
- Result logging

---

## Recommendations

### 1. Create Shared Utilities (HIGH PRIORITY)

**Before doing experiment 40+, abstract the patterns from 1-39.**

```
src/ml/
├── utils/
│   ├── __init__.py
│   ├── constants.py      # BASIC_LANDS, paths
│   ├── data_loading.py   # load_pairs, load_embeddings, load_test_set
│   ├── similarity.py     # jaccard, cosine, filtered variants
│   ├── evaluation.py     # standard evaluation loop
│   └── experiment.py     # ClosedLoopExperiment helpers
```

**Rationale:** We've experienced 19 experiments. That's enough to know the patterns.

### 2. Add Python Tests (HIGH PRIORITY)

**Minimum viable:**
```
src/ml/tests/
├── test_evaluation.py      # P@10, MRR calculations
├── test_similarity.py      # Jaccard, cosine correctness
├── test_data_loading.py    # Path consistency
└── test_integration.py     # End-to-end smoke test
```

**Why critical:** Current results have no automated verification. A bug in evaluation metric would invalidate all experiments.

### 3. Standardize Experiment Logging

**Pick ONE canonical log:**
- Either `EXPERIMENT_LOG.jsonl` (simple) or `EXPERIMENT_LOG_EVOLVED.jsonl` (rich)
- Update all experiments to use it
- Remove duplicates

### 4. Consolidate Paths

**Create config.py:**
```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PAIRS_FILE = DATA_DIR / "processed" / "pairs_large.csv"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
```

Use consistently across all experiments.

### 5. Document When to Abstract

**Add to PRINCIPLES.md:**

```markdown
## When to Abstract

Experience complexity before abstracting, BUT:

**Abstract when:**
- Pattern appears 3+ times
- Inconsistency causes bugs
- Onboarding requires explaining duplicated code

**Don't abstract when:**
- Only 1-2 instances
- Requirements still evolving
- Cost > benefit
```

---

## Grade by Principle

| Principle | Backend (Go) | ML (Python) | Overall |
|-----------|--------------|-------------|---------|
| Experience before abstracting | A | **D** | C |
| Significant critique | A | B+ | A- |
| Honest assessment | A | A | A |
| Data quality focus | A | B+ | A- |
| Tests for regression | A | **D** | C+ |

**Overall Backend:** A (walks the talk)
**Overall ML:** C- (doesn't walk the talk)
**System:** B- (mixed)

---

## Bottom Line

**The Go backend exemplifies the principles.**
- Proper abstraction after experiencing pain
- Comprehensive tests
- Clean structure

**The Python ML code violates them.**
- Massive duplication (19 scripts, no shared utils)
- Minimal testing (1 file for 10K lines)
- Inconsistent paths and evaluation

**This is understandable** - rapid experimentation mode. But after 39 experiments, it's time to consolidate learnings into reusable infrastructure.

---

## Next Steps

**Immediate (Before Experiment 40):**
1. Create `src/ml/utils/` with constants, data loading, evaluation
2. Refactor 2-3 recent experiments to use shared utils
3. Add basic tests for evaluation metrics
4. Pick canonical experiment log

**This Week:**
5. Add pytest to requirements.txt
6. Create test suite (10-15 tests minimum)
7. Document standard experiment structure
8. Clean up duplicate logs

**Rationale:** Following our own principle - we've experienced enough complexity. Time to abstract based on real pain points, not speculation.

---

## Positive Note

The **architecture is sound:**
- Clean separation (Go/Python boundary)
- Multi-game support works
- Experiment tracking system exists

The issue is **implementation discipline** in the rapid experimentation phase. This is fixable and expected. The awareness (this review) is the first step to alignment.
