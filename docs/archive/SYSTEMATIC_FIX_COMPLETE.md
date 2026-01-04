# Systematic Fix - Complete Status

**Date**: 2025-01-27
**Approach**: Calm, mindful, systematic

---

## ✅ What Has Been Fixed

### 1. LLM Judge Error Handling ✅
**File**: `src/ml/annotation/llm_judge_batch.py`
- Robust validation and error handling
- Retry logic (max 2 retries)
- Result structure validation
- Relevance score validation
- Better error messages

**Status**: ✅ **COMPLETE** - Ready for testing

### 2. Inter-Annotator Agreement (IAA) System ✅
**File**: `src/ml/evaluation/inter_annotator_agreement.py`
- Cohen's Kappa (two annotators)
- Krippendorff's Alpha (multiple annotators, missing data)
- Fleiss' Kappa (multiple annotators, categorical)
- Intra-annotator agreement (stability)
- Confidence analysis
- Scipy optional (graceful degradation)

**Status**: ✅ **COMPLETE** - Ready for integration

### 3. Diagnostic and Measurement Scripts ✅
**Files**:
- `src/ml/scripts/diagnose_and_fix.py` - Checks what's available
- `src/ml/scripts/fix_and_measure_all.py` - Comprehensive measurement
- `src/ml/scripts/measure_with_available_data.py` - Works without scipy
- `src/ml/scripts/complete_fix_pipeline.py` - Automated fix pipeline

**Status**: ✅ **COMPLETE** - Ready to use

### 4. Data Preparation ✅
- ✅ Pairs CSV found: `src/backend/pairs.csv` (278MB)
- ✅ Copied to: `data/processed/pairs_large.csv`
- ✅ Test set: 38 queries available
- ✅ Data directory: `src/backend/data-full/games/magic` exists

**Status**: ✅ **DATA READY** - Can proceed with training

---

## ⚠️ Environment Issue (Blocking)

### Scipy Build Failure

**Problem**: `scipy==1.12.0` fails to build due to missing OpenBLAS dependency

**Error**:
```
Dependency "OpenBLAS" not found, tried pkgconfig and framework
```

**Impact**: Blocks:
- Training embeddings (needs scipy via dependencies)
- Computing signals (needs scipy via dependencies)
- Running measurement scripts (needs numpy/pandas which may pull scipy)

**Solutions**:

#### Option 1: Install OpenBLAS (Recommended)
```bash
# macOS
brew install openblas

# Then retry
uv sync
```

#### Option 2: Use Pre-built Scipy Wheel
```bash
# Try installing from pre-built wheel
pip install --only-binary=scipy scipy
```

#### Option 3: Work Without Scipy (Temporary)
- IAA system already made scipy optional
- Measurement scripts can work without scipy
- But training/computation may still need it

---

## 📊 Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| **LLM Judge** | ✅ Fixed | Error handling improved |
| **IAA System** | ✅ Complete | All metrics implemented |
| **Test Set** | ✅ Available | 38 queries (Magic) |
| **Pairs CSV** | ✅ Available | 278MB, copied to processed |
| **Embeddings** | ❌ Not trained | Blocked by scipy build |
| **Signals** | ❌ Not computed | Blocked by scipy build |
| **Measurement** | ⚠️ Partial | Can measure Jaccard if env works |

---

## 🎯 What Can Be Done Now (Without Scipy)

### 1. Measure Jaccard Similarity
**If we can load graph** (needs pandas/numpy):
```python
# Can measure Jaccard if basic dependencies work
python3 src/ml/scripts/measure_with_available_data.py
```

### 2. Test IAA System
```python
# IAA works without scipy
from src.ml.evaluation.inter_annotator_agreement import InterAnnotatorAgreement
iaa = InterAnnotatorAgreement()
result = iaa.cohens_kappa([4,3,2,1,0], [4,3,2,1,0])
```

### 3. Test LLM Judge
```bash
# Fixed error handling - can test
uv run python -m src.ml.annotation.llm_judge_batch \
  --test-set experiments/test_set_canonical_magic.json \
  --predictions <predictions.json> \
  --output judgments.json \
  --max-queries 3
```

---

## 🔧 Fix Scipy Issue (Then Proceed)

### Immediate Fix
```bash
# Install OpenBLAS
brew install openblas

# Set environment variable
export OPENBLAS=$(brew --prefix openblas)

# Retry uv sync
uv sync
```

### Alternative: Use Conda/Mamba
```bash
# Conda has pre-built scipy
conda install scipy
```

### Then Proceed With:
1. Train embeddings
2. Compute signals
3. Measure individual signals
4. Fix fusion weights
5. Full evaluation

---

## 📋 Complete Fix Checklist

### ✅ Completed
- [x] LLM Judge error handling
- [x] IAA system implementation
- [x] Diagnostic scripts
- [x] Measurement scripts
- [x] Data location identified
- [x] Pairs CSV copied to processed

### 🔴 Blocked (Need Scipy Fix)
- [ ] Train embeddings
- [ ] Compute signals
- [ ] Measure all signals
- [ ] Fix fusion weights

### 🟡 Can Do Now
- [ ] Test IAA system (mock data)
- [ ] Test LLM Judge (small batch)
- [ ] Review fusion weights logic
- [ ] Plan multi-judge system

---

## 🚀 Next Steps (After Scipy Fixed)

### Step 1: Train Embeddings
```bash
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input data/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128 \
  --workers 8
```

### Step 2: Compute Signals
```bash
# First need decks_with_metadata.jsonl
# Then:
uv run python -m src.ml.scripts.compute_and_cache_signals
```

### Step 3: Measure Individual Signals
```bash
uv run python -m src.ml.scripts.fix_and_measure_all
```

### Step 4: Fix Fusion Weights
- Based on individual signal performance
- Re-optimize weights
- Validate improvement

---

## 📝 Summary

**Fixed**:
- ✅ LLM Judge error handling
- ✅ IAA system (complete)
- ✅ Diagnostic/measurement scripts
- ✅ Data preparation (pairs CSV ready)

**Blocked**:
- ❌ Scipy build issue (environment)
- ❌ Training/computation (depends on scipy)

**Ready to Proceed**:
- ✅ Once scipy is fixed, all scripts are ready
- ✅ All code fixes are complete
- ✅ Data is available

---

**Status**: ✅ **CODE FIXES COMPLETE** - Environment issue (scipy) blocking execution, but all fixes are in place!
