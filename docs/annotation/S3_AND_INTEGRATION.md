# Annotation S3 Sync and System Integration

## Overview

All annotations are automatically synced to S3 and integrated with the training and evaluation systems.

## S3 Sync

### Location
- **S3 Bucket**: `s3://games-collections/annotations/`
- **Local Directory**: `annotations/`

### Syncing Annotations

```bash
# Sync all annotations to S3
python3 scripts/annotation/sync_to_s3.py \
    --annotations-dir annotations \
    --s3-path s3://games-collections/annotations/

# Dry run (see what would be synced)
python3 scripts/annotation/sync_to_s3.py \
    --annotations-dir annotations \
    --s3-path s3://games-collections/annotations/ \
    --dry-run
```

### What Gets Synced

- All `*_llm_annotations.jsonl` files (Magic, Pokemon, Yu-Gi-Oh, Riftbound)
- Hand annotation YAML files (`hand_batch_*.yaml`)
- Quality reports and analytics (`*quality*.json`, `*tracking*.json`)
- Integrated annotation files
- Test results and validation reports

## Integration with Training System

### Step 1: Integrate All Annotations

```bash
# Integrate all annotation sources into unified format
python3 scripts/annotation/integrate_all_annotations.py \
    --annotations-dir annotations \
    --output annotations/integrated_all.jsonl
```

This creates `annotations/integrated_all.jsonl` with all annotations from:
- LLM annotations (single and multi-annotator)
- Hand annotations
- User feedback
- Multi-judge annotations

### Step 2: Convert to Training Data

```bash
# Convert integrated annotations to training data format
python3 scripts/annotation/convert_to_training_data.py \
    --annotation-path annotations/integrated_all.jsonl \
    --output data/processed/training_data_from_annotations.jsonl \
    --min-score 0.0 \
    --game magic  # Optional: filter by game
```

This:
- Filters out test set cards (prevents data leakage)
- Converts to training example format
- Adds weights based on annotation source quality
- Saves in format ready for training scripts

### Step 3: Validate Before Training

```bash
# Validate training data for leakage
python3 scripts/training/validate_training_data.py \
    --annotation-path data/processed/training_data_from_annotations.jsonl \
    --check-leakage
```

### Step 4: Use in Training

Training scripts can use the converted training data:

```bash
# Example: Use annotations in training
python3 scripts/training/train_multitask_refined.py \
    --similarity-annotations data/processed/training_data_from_annotations.jsonl \
    --other-args...
```

## Complete Workflow

Use the automated script to do everything:

```bash
# Sync to S3 and integrate
python3 scripts/annotation/ensure_s3_and_integration.py
```

This script:
1. ✅ Syncs all annotations to S3
2. ✅ Integrates all annotation sources
3. ✅ Validates annotations for training use
4. ✅ Provides summary and next steps

## Annotation Sources

Current annotation sources (all integrated):

1. **LLM Annotations** (`*_llm_annotations.jsonl`)
   - Single annotator: `source: "llm"`
   - Multi-annotator: `source: "llm_multi_annotator"`
   - Agentic meta-judge: `source: "llm_multi_annotator_agentic"`

2. **Hand Annotations** (`hand_batch_*.yaml`)
   - Human-annotated with 0-4 relevance scale
   - Converted to 0-1 similarity scores

3. **User Feedback** (`user_feedback.jsonl`)
   - UI-based feedback annotations
   - Highest quality weight (2.0)

4. **Multi-Judge Annotations**
   - Multiple judge consensus
   - IAA metrics included

## Quality Weights

Annotations are weighted by source quality in training:

- **Hand annotations**: 2.0 (highest quality)
- **User feedback**: 2.0 (highest quality)
- **Multi-annotator agentic**: 1.5 (high quality, consensus)
- **Multi-annotator**: 1.5 (high quality, consensus)
- **Single LLM**: 1.0 (default)

## Data Leakage Prevention

**CRITICAL**: All annotations are automatically filtered to exclude test set cards before training.

The `convert_to_training_data.py` script:
- Loads test set cards from all games
- Filters out any annotation containing a test set card
- Logs filtered annotations for review
- Ensures evaluation validity

## S3 Backup

All annotations are backed up to S3:
- **Location**: `s3://games-collections/annotations/`
- **Frequency**: Run `ensure_s3_and_integration.py` after generating new annotations
- **Access**: Use `s5cmd` or AWS CLI to download from S3

## Current Status

- ✅ **158 annotation files** synced to S3
- ✅ **48 integrated annotations** ready for training
- ✅ **All games supported**: Magic, Pokemon, Yu-Gi-Oh, Riftbound
- ✅ **Multi-annotator IAA** annotations included
- ✅ **Agentic meta-judge** annotations included
- ✅ **Test set filtering** implemented
- ✅ **Training data conversion** ready

## Next Steps

1. Generate more annotations across all games
2. Convert to training data format
3. Validate for leakage
4. Use in training scripts
5. Monitor quality trends
