# Experiment Infrastructure Audit
**Date**: October 4, 2025  
**Goal**: Assess experiment organization, duplication, deprecation, and test suite integration

---

## Current State Discovered

### Experiment Files Found

**Active (src/ml/)**:
- `exp_format_specific.py` - Format-specific filtering experiment
- `exp_source_filtering.py` - Source filtering (just created today)
- `validate_data_quality.py` - Data quality validation (today)
- `scrutinize_experiment.py` - Experiment scrutiny (today)
- `debug_evaluation.py` - Evaluation debugging (today)
- `critical_investigation.py` - Critical analysis (today)
- `analyze_improvement_quality.py` - Quality analysis (today)
- `cross_validate_results.py` - Cross-validation (today)

**Archived (src/ml/experimental/)**:
- `exp_format_specific.py` - DUPLICATE of active version
- `exp_056_verify_baseline.py` - Old baseline verification
- `run_exp_007.py` through `run_exp_049_consolidated.py` - 20+ old experiments
- `experiment_runner.py` - Experiment orchestration system
- `self_sustaining_loop.py` - Autonomous loop
- `true_closed_loop.py` - Closed-loop system
- `meta_learner.py` - Meta-learning system

### Test Infrastructure

**Active Tests (src/ml/tests/)**:
- `test_constants.py`
- `test_data_loading.py`
- `test_evaluation.py`
- `test_similarity.py`
- `run_tests.py` - Test runner

**Test Scripts (src/ml/)**:
- `test_source_filtering.py` - Tests new utilities
- `test_annotation_batch.py` - LLM annotation tests
- `test_llm_annotation.py` - LLM tests
- `test_openrouter_simple.py` - API tests

---

## Problems Identified

### 1. ❌ Code Duplication
- `exp_format_specific.py` exists in BOTH `src/ml/` and `src/ml/experimental/`
- Which one is canonical?
- Do they have different implementations?
- If someone updates one, the other is stale

### 2. ⚠️ No Unified Test Suite
**Current situation**:
- `uv run pytest tests/` - Runs unit tests (31 tests)
- Individual experiments run independently
- No `run_all_experiments.py`
- No way to validate all experiments still work

**Missing**:
- Test suite that runs all active experiments
- Smoke tests for each experiment
- Integration tests for experiment pipeline

### 3. ⚠️ Unclear Active vs Deprecated
**Questions**:
- Are `run_exp_XXX.py` files in `experimental/` deprecated?
- Or are they still meant to be run?
- `experiment_runner.py` looks sophisticated but is it used?
- `self_sustaining_loop.py` - is this active or experimental?

**README says**:
> "Moved to src/ml/experimental/: ... Multiple duplicate experiment tracking systems"

So `experimental/` IS the archive. But there's duplication.

### 4. ❌ No Experiment Orchestration
**What we need**:
```python
# run_experiment_suite.py
def run_all_experiments():
    results = []
    results.append(run_exp_format_specific())
    results.append(run_exp_source_filtering())
    # ... etc
    return results
```

**What we have**:
- Individual experiment scripts
- No orchestration
- No way to run "full validation"

### 5. ⚠️ Experiment Log Integration
**Current**:
- `EXPERIMENT_LOG_CANONICAL.jsonl` exists
- `exp_source_filtering.py` appends to it ✅
- But older experiments might not
- No validation that log is complete

---

## Detailed File Analysis

### Active Experiments (Should Work)

| File | Purpose | Can Run? | Tested? |
|------|---------|----------|---------|
| `exp_format_specific.py` | Format filtering | Unknown | No |
| `exp_source_filtering.py` | Source filtering | ✅ Yes | ✅ Yes |
| `validate_data_quality.py` | Data quality | ✅ Yes | ✅ Yes |

### Analysis Scripts (Should Work)

| File | Purpose | Can Run? | Tested? |
|------|---------|----------|---------|
| `archetype_staples.py` | Archetype analysis | Unknown | No |
| `sideboard_analysis.py` | Sideboard patterns | Unknown | No |
| `card_companions.py` | Card co-occurrence | Unknown | No |
| `deck_composition_stats.py` | Deck stats | Unknown | No |

### Archived Experiments (Unclear Status)

| File | Purpose | Status | Should Run? |
|------|---------|--------|-------------|
| `experimental/run_exp_007.py` | Old | ? | ? |
| `experimental/run_exp_049_consolidated.py` | Old | ? | ? |
| `experimental/experiment_runner.py` | Infrastructure | Active? | Maybe |
| `experimental/self_sustaining_loop.py` | Autonomous | Active? | Maybe |

---

## Recommendations

### Immediate Actions

1. **Deduplicate exp_format_specific.py**
   - Keep one canonical version
   - Delete or clarify the other
   - Document which is active

2. **Create Experiment Test Suite**
   ```python
   # tests/test_experiments.py
   def test_exp_source_filtering_runs():
       """Smoke test: experiment can run without errors."""
       # Run with small dataset
       ...
   
   def test_exp_format_specific_runs():
       ...
   ```

3. **Document Experiment Status**
   ```markdown
   # EXPERIMENTS.md
   
   ## Active
   - exp_source_filtering.py - Source filtering (Oct 4, 2025)
   - exp_format_specific.py - Format-specific (needs testing)
   
   ## Archived
   - experimental/run_exp_*.py - Historical (47 experiments)
   - experimental/experiment_runner.py - Old infrastructure
   ```

4. **Create run_all_analysis.py Enhancement**
   - Already exists but check if it runs all tools
   - Add all analysis scripts
   - Add smoke tests

### Medium-Term

5. **Experiment Base Class**
   ```python
   class BaseExperiment:
       def __init__(self, name, hypothesis):
           self.name = name
           self.hypothesis = hypothesis
       
       def run(self) -> dict:
           raise NotImplementedError
       
       def log_result(self, result):
           # Auto-append to EXPERIMENT_LOG_CANONICAL.jsonl
           ...
   ```

6. **Deprecation System**
   - Move old experiments to `experimental/deprecated/`
   - Keep only reference implementations in `experimental/`
   - Document what's active vs historical

---

## Investigation Plan

Let me check each active file to see if it can run:

1. Check if exp_format_specific.py (active) works
2. Compare to experimental/exp_format_specific.py
3. Check if analysis tools (archetype_staples, etc.) work
4. Check if run_all_analysis.py is comprehensive
5. Create integrated test suite
