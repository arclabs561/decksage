# Annotations Integration Summary

## Current State

### Files Found
- **LLM Annotations (JSONL)**: 2 files
  - `riftbound_llm_annotations.jsonl`
  - `yugioh_llm_annotations.jsonl`
  
- **Hand Annotations (YAML)**: 9 files
  - `hand_batch_magic_enhanced.yaml`
  - `hand_batch_pokemon.yaml` (+ enhanced, retrofitted variants)
  - `hand_batch_yugioh.yaml` (+ enhanced, retrofitted variants)
  - `batch_001_initial.yaml`
  - `batch_auto_generated.yaml`

- **LLM Judgments (JSON)**: 1 file
  - `llm_judgments/judgment_20251001_105332.json`

### S3 Storage
- **LLM Annotations**: `s3://games-collections/experiments/annotations_llm/`
- **Hand Annotations**: `s3://games-collections/annotations/`
- **Sync Script**: `scripts/sync_llm_annotations_to_s3.sh`

## Integration Status

### ✅ Fully Integrated

1. **Data Lineage** (`data/DATA_LINEAGE_METADATA.json`)
   - Tracks all formats: JSONL, YAML, JSON (judgments)
   - Documents S3 paths
   - Conversion paths documented

2. **Conversion Utilities** (`src/ml/utils/annotation_utils.py`)
   - Auto-detects format (JSONL vs YAML)
   - Converts to substitution pairs
   - Supports both formats

3. **Training Integration**
   - `train_multitask_refined_enhanced`: Full support via `--similarity-annotations`
   - `train_hybrid_full`: Accepts annotations, logs for reference

4. **Test Set Merging**
   - `hand_annotate merge`: Converts YAML to test sets

### ⚠️ Partially Integrated

1. **LLM Judgments**
   - Created by `progressive_annotation.py` and `multi_perspective_judge.py`
   - Can be converted via `integrate_all_annotations.py`
   - Not automatically integrated into workflow

2. **S3 Sync**
   - Scripts exist but may not be automated
   - Paths documented in data lineage

### 🔧 New Tools Created

1. **`integrate_all_annotations.py`**
   - Integrates all annotation types (JSONL, YAML, Judgments)
   - Converts to substitution pairs and/or test sets
   - Usage: `python -m src.ml.scripts.integrate_all_annotations --help`

## Data Flow

```
LLM Annotations (JSONL)
    ↓
Hand Annotations (YAML)
    ↓
LLM Judgments (JSON) ──→ [integrate_all_annotations] ──→ Unified Format
    ↓
[convert_annotations_to_substitution_pairs]
    ↓
Substitution Pairs (JSON)
    ↓
Training (2x weight)
```

```
Hand Annotations (YAML)
    ↓
[hand_annotate merge]
    ↓
Test Sets (Order 5)
    ↓
Evaluation
```

## Next Steps

1. **Verify Usage**: Check if existing YAML files have been converted/merged
2. **Automate Workflow**: Create scheduled job to process new annotations
3. **Monitor Integration**: Track which annotations are used in training

## Quick Reference

### Convert All Annotations
```bash
python -m src.ml.scripts.integrate_all_annotations \
    --annotations-dir annotations \
    --output-substitution-pairs experiments/substitution_pairs_all.json \
    --output-test-set experiments/test_set_all.json
```

### Use in Training
```bash
python -m src.ml.scripts.train_multitask_refined_enhanced \
    --pairs data/processed/pairs_large.csv \
    --similarity-annotations annotations/hand_batch_magic_enhanced.yaml \
    --output data/embeddings/multitask_with_annotations.wv
```

### Merge to Test Set
```bash
python -m src.ml.annotation.hand_annotate merge \
    --input annotations/hand_batch_magic_enhanced.yaml \
    --test-set experiments/test_set_unified_magic.json
```
