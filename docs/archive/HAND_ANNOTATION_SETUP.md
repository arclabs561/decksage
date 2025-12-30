# Hand Annotation Setup Complete ✅

## What Was Created

### 1. Hand Annotation Tool (`src/ml/annotation/hand_annotate.py`)
- **Generate**: Creates annotation batches with candidate cards
- **Grade**: Validates and grades completed annotations
- **Merge**: Merges annotations into canonical test sets

### 2. Batch Generator (`src/ml/scripts/generate_all_annotation_batches.py`)
- Automatically generates batches for all games
- Targets: 50 MTG, 25 Pokemon, 25 YGO (100 total)
- Excludes existing queries to avoid duplicates

### 3. Enhanced Evaluation (`src/ml/utils/evaluation.py`)
- Added `evaluate_with_confidence()` function
- Bootstrap confidence intervals (95% CI)
- Backward compatible with existing code

### 4. Documentation (`annotations/README.md`)
- Complete workflow guide
- Annotation guidelines
- Quality checklists

## Usage

### Step 1: Install Dependencies
```bash
cd /Users/arc/Documents/dev/decksage
uv sync  # or: pip install -r requirements.txt
```

### Step 2: Generate Annotation Batches
```bash
python -m src.ml.scripts.generate_all_annotation_batches
```

This creates:
- `annotations/hand_batch_magic_expansion.yaml` (12 new queries)
- `annotations/hand_batch_pokemon_expansion.yaml` (15 new queries)
- `annotations/hand_batch_yugioh_expansion.yaml` (12 new queries)

### Step 3: Hand Annotate
Open each YAML file and grade candidates (0-4 scale):
- **4**: Extremely similar (near substitutes)
- **3**: Very similar (often together)
- **2**: Somewhat similar (related function)
- **1**: Marginally similar (loose connection)
- **0**: Irrelevant

### Step 4: Grade & Validate
```bash
python -m src.ml.annotation.hand_annotate grade \
    --input annotations/hand_batch_magic_expansion.yaml
```

### Step 5: Merge to Test Sets
```bash
python -m src.ml.annotation.hand_annotate merge \
    --input annotations/hand_batch_magic_expansion.yaml \
    --test-set experiments/test_set_canonical_magic.json
```

## Current Status

| Game | Current | Target | Needed | Batch File |
|------|---------|--------|--------|------------|
| MTG | 38 | 50 | 12 | `hand_batch_magic_expansion.yaml` |
| Pokemon | 10 | 25 | 15 | `hand_batch_pokemon_expansion.yaml` |
| Yu-Gi-Oh | 13 | 25 | 12 | `hand_batch_yugioh_expansion.yaml` |
| **Total** | **61** | **100** | **39** | |

## Next Steps

1. ✅ **Tool Created** - Hand annotation system ready
2. ⏳ **Install Dependencies** - Run `uv sync` or equivalent
3. ⏳ **Generate Batches** - Run batch generator
4. ⏳ **Hand Annotate** - Grade all 39 new queries
5. ⏳ **Merge & Validate** - Merge into test sets
6. ⏳ **Re-evaluate** - Run evaluation with confidence intervals

## Integration

Once annotations are merged, evaluation automatically uses:
- Bootstrap confidence intervals (1000 samples)
- Statistical rigor (95% CI)
- Expanded test sets (100+ queries)

Example output:
```
P@10: 0.0882 (95% CI: 0.0751, 0.1013)
nDCG@10: 0.1234 (95% CI: 0.1100, 0.1368)
```

## Files Created

- `src/ml/annotation/hand_annotate.py` - Main annotation tool
- `src/ml/scripts/generate_all_annotation_batches.py` - Batch generator
- `annotations/README.md` - Workflow documentation
- `src/ml/utils/evaluation.py` - Enhanced with CI support

