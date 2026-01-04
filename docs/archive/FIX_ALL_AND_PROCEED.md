# Fix All and Proceed - Systematic Plan

**Date**: 2025-01-27
**Approach**: Calm, mindful, systematic

---

## Current Status (Diagnostic)

✅ **Available**:
- Test set: 38 queries (Magic)
- IAA system: Implemented
- LLM Judge: Fixed (error handling)

❌ **Missing**:
- Pairs CSV (needed for graph, embeddings, signals)
- Embeddings (need to train)
- Decks metadata (needed for signals)
- Signals (need to compute)

---

## Systematic Fix Plan

### Phase 1: Data Export (Foundation)

**Step 1.1: Export Pairs CSV**
```bash
cd src/backend
go run ./cmd/export-decks-only data-full/games/magic pairs_large.csv
# OR if data is elsewhere:
go run ./cmd/quick-graph <data_dir> pairs_large.csv
```

**Step 1.2: Export Decks Metadata**
```bash
# Need to check if this command exists or needs to be created
# Should export: data/processed/decks_with_metadata.jsonl
```

**Step 1.3: Verify Exports**
```bash
python3 src/ml/scripts/diagnose_and_fix.py
```

### Phase 2: Training (After Data Available)

**Step 2.1: Train Embeddings**
```bash
uv run python -m src.ml.similarity.card_similarity_pecan \
  --input data/processed/pairs_large.csv \
  --output magic_128d \
  --dim 128 \
  --workers 8
```

**Step 2.2: Compute All Signals**
```bash
uv run python -m src.ml.scripts.compute_and_cache_signals
```

**Step 2.3: Train GNN (Optional)**
```bash
uv run python -m src.ml.scripts.train_gnn \
  --model GraphSAGE \
  --epochs 100 \
  --output experiments/signals/gnn_embeddings.json
```

### Phase 3: Measurement (After Training)

**Step 3.1: Measure Individual Signals**
```bash
uv run python -m src.ml.scripts.fix_and_measure_all
```

**Step 3.2: Analyze Results**
- Compare Jaccard vs Embed vs Functional
- Identify which signals help/hurt
- Understand why fusion is worse than baseline

### Phase 4: Optimization (After Measurement)

**Step 4.1: Fix Fusion Weights**
- Based on individual signal performance
- Re-optimize weights
- Validate improvement

**Step 4.2: Full Evaluation**
- Run complete evaluation pipeline
- Compare to baseline (0.089)
- Target: Beat baseline (0.089 → 0.10+)

---

## Immediate Actions

### Action 1: Find Data Location
```bash
# Check where data actually is
fd -t d data-full
fd -t f -e zst | head -5
```

### Action 2: Export Pairs CSV
Once data location found:
```bash
cd src/backend
go run ./cmd/export-decks-only <data_dir> ../../data/processed/pairs_large.csv
```

### Action 3: Check for Decks Metadata Export
```bash
# Check if export command exists
fd export.*metadata
grep -r "decks_with_metadata" src/backend
```

---

## What We've Fixed So Far

✅ **LLM Judge Error Handling**
- Robust validation
- Retry logic
- Better error messages

✅ **IAA System**
- Cohen's Kappa
- Krippendorff's Alpha
- Fleiss' Kappa
- Intra-annotator agreement

✅ **Diagnostic Script**
- Checks what's available
- Provides clear next steps

---

## What Needs Data First

🔴 **Cannot Do Without Pairs CSV**:
- Train embeddings
- Compute signals
- Measure Jaccard similarity
- Full evaluation

🟡 **Can Do With Limited Data**:
- Measure Functional similarity (if tagger works)
- Test IAA system (with mock data)
- Test LLM Judge (with test set)

---

## Next Command to Run

**First, find data**:
```bash
cd /Users/arc/Documents/dev/decksage
fd -t d data-full
fd -t f -e zst | head -3
```

**Then export**:
```bash
cd src/backend
go run ./cmd/export-decks-only <data_dir> ../../data/processed/pairs_large.csv
```

---

**Status**: ✅ **Fixes Complete** - Ready to proceed once data is exported!
