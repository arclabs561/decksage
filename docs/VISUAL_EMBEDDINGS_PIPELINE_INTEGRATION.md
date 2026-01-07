# Visual Embeddings: Pipeline Integration

**Date:** January 6, 2026

## Overview

Visual embeddings are now integrated into the standard data processing pipeline, not as one-off scripts. Image URL fetching is part of card attribute enrichment.

## Pipeline Integration Points

### 1. Card Attribute Loading (`src/ml/utils/data_loading.py`)

The canonical `load_card_attributes()` function now supports optional image URL enrichment:

```python
from ml.utils.data_loading import load_card_attributes

# Standard loading
card_attrs = load_card_attributes()

# With image URL enrichment (for Magic cards)
card_attrs = load_card_attributes(enrich_with_images=True, game="magic")
```

**Behavior:**
- Loads from `data/processed/card_attributes_enriched.csv`
- Optionally fetches missing image URLs from Scryfall API
- Resumes automatically (skips cards that already have URLs)
- Adds `image_url` field to card attributes dict

### 2. Data Processing Script (`scripts/data/update_card_data_with_images.py`)

Updated to be part of the standard pipeline:

- Uses canonical paths (`PATHS.card_attributes`)
- Updates CSV in-place by default (or to specified output)
- Integrates with data lineage (Order 0-1: Card attributes enrichment)
- Supports test-set-only mode for focused enrichment

**Usage:**
```bash
# Enrich all cards
just enrich-card-images

# Enrich test set cards only
just enrich-card-images test-set-only

# Limit for testing
just enrich-card-images limit=100
```

### 3. Scryfall Utilities (`src/ml/utils/scryfall_image_urls.py`)

Reusable utilities for image URL fetching:

- `get_scryfall_image_url()`: Fetch single card image URL
- `enrich_card_attributes_with_images()`: Batch enrichment with progress tracking

**Features:**
- Rate limiting (0.1s delay per request)
- Retry logic with exponential backoff
- Resume support (skips existing URLs)
- Progress reporting

## Data Flow

```
Order 0: Primary Source Data
  └─> Card attributes from Scryfall API
       └─> card_attributes_enriched.csv

Order 0-1: Card Attribute Enrichment
  └─> Image URL fetching (optional)
       └─> Updates card_attributes_enriched.csv with image_url column
            └─> Used by CardVisualEmbedder for visual embeddings

Order 4: Embeddings
  └─> Visual embeddings (uses image_url from card attributes)
       └─> Integrated into WeightedLateFusion
```

## Integration with Existing Code

### Card Attribute Loading

All existing code that loads card attributes can now optionally enrich with images:

```python
# Before (scattered implementations)
card_attrs = load_card_attributes_from_csv(path)  # Various implementations

# After (canonical implementation)
from ml.utils.data_loading import load_card_attributes
card_attrs = load_card_attributes(enrich_with_images=True)
```

### Visual Embedder

`CardVisualEmbedder` automatically uses `image_url` from card attributes:

```python
# Card attributes dict with image_url
card = {"name": "Lightning Bolt", "image_url": "https://..."}

# Visual embedder extracts and uses it
embedder = CardVisualEmbedder()
embedding = embedder.embed_card(card)  # Uses image_url automatically
```

## Pipeline Commands

### Standard Workflow

```bash
# 1. Enrich card attributes with image URLs
just enrich-card-images

# 2. Load card attributes (with images)
python -c "
from ml.utils.data_loading import load_card_attributes
attrs = load_card_attributes()  # image_url included if available
"

# 3. Visual embeddings automatically use image_url
# (No code changes needed - CardVisualEmbedder extracts from card dict)
```

### Test Set Focused

```bash
# Enrich only test set cards (faster, focused)
just enrich-card-images test-set-only

# Then run evaluation
python scripts/evaluation/run_visual_evaluation_simple.py
```

## Benefits of Pipeline Integration

1. **No One-Off Scripts**: Image URL fetching is part of standard data processing
2. **Canonical Paths**: Uses `PATHS.card_attributes` consistently
3. **Resume Support**: Can run multiple times, only fetches missing URLs
4. **Progress Tracking**: Built-in progress reporting and statistics
5. **Error Handling**: Graceful degradation, doesn't break pipeline
6. **Integration**: Works seamlessly with existing card attribute loading

## Migration from One-Off Scripts

**Removed:**
- `scripts/data/fetch_test_set_images.py` (consolidated into pipeline)

**Updated:**
- `scripts/data/update_card_data_with_images.py` (now uses canonical paths, part of pipeline)
- `src/ml/utils/data_loading.py` (added `load_card_attributes()` with image enrichment)

**New:**
- `src/ml/utils/scryfall_image_urls.py` (reusable utilities)
- `just enrich-card-images` (pipeline command)

## Next Steps

1. **Run enrichment**: `just enrich-card-images` to fetch image URLs
2. **Verify coverage**: `python scripts/analysis/analyze_visual_coverage.py`
3. **Run evaluation**: Evaluate visual embeddings with improved coverage
4. **Optimize weights**: Run optimization with visual embeddings enabled

## Data Lineage

Image URL enrichment is part of **Order 0-1: Card Attribute Enrichment**:
- Depends on: Order 0 (Primary Source Data)
- Produces: Enriched card attributes with `image_url` field
- Used by: Order 4 (Visual Embeddings), Order 6 (Annotations)

