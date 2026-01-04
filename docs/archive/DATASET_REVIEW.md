# Dataset Review

**Date**: 2025-01-27
**Reviewer**: AI Assistant
**Scope**: All datasets in `/data` directory

## Executive Summary

The dataset collection has several critical gaps that limit evaluation and model training capabilities. The ground truth dataset is extremely small (5 queries), two key datasets are empty, and there are data format inconsistencies.

## Dataset Inventory

### 1. Ground Truth Dataset (`data/processed/ground_truth_v1.json`)

**Status**: ⚠️ **CRITICAL LIMITATION**

- **Size**: 4KB, 113 lines
- **Queries**: 5 total
  - Lightning Bolt
  - Brainstorm
  - Dark Ritual
  - Force of Will
  - Delver of Secrets
- **Structure**: Well-formed JSON with 5 relevance levels per query
  - `highly_relevant`
  - `relevant`
  - `somewhat_relevant`
  - `marginally_relevant`
  - `irrelevant`

**Issues**:
- **Extremely small sample size**: 5 queries is insufficient for reliable evaluation
- **No confidence intervals possible**: With n=5, statistical significance cannot be established
- **Limited coverage**: Only covers 5 Magic: The Gathering cards
- **Single game**: Only MTG, no Pokemon or Yu-Gi-Oh ground truth

**Impact**:
- Current P@10=0.0882 metric has no statistical validity
- Cannot detect improvements or regressions reliably
- Cannot perform cross-game evaluation

**Recommendations**:
1. Expand to at least 50-100 queries per game
2. Include Pokemon and Yu-Gi-Oh queries
3. Ensure balanced coverage across card types and archetypes
4. Add metadata (query source, annotation method, date)

### 2. Yu-Gi-Oh Deck Dataset (`data/decks/yugioh_decks.jsonl`)

**Status**: ⚠️ **FORMAT ISSUE**

- **Size**: 56KB
- **Decks**: 20 total
- **Structure**: Valid JSONL with fields:
  - `deck_id`, `archetype`, `format`, `url`, `source`, `cards`
  - Cards include `name`, `count`, `partition` (Main Deck/Extra Deck/Side Deck)

**Issues**:
- **Numeric card IDs**: Cards use format `Card_11765832` instead of card names
- **Small sample**: Only 20 decks
- **No card name mapping**: Cannot match to card database or ground truth

**Impact**:
- Cannot use for similarity search (no card names)
- Cannot validate against ground truth
- Limited training data

**Recommendations**:
1. Add card name mapping (ID → name)
2. Expand dataset to 1000+ decks
3. Include card metadata (type, attribute, level, etc.)

### 3. Pokemon Deck Dataset (`data/processed/decks_pokemon.jsonl`)

**Status**: ❌ **EMPTY**

- **Size**: 0 bytes, 0 lines
- **Status**: File exists but contains no data

**Impact**:
- No Pokemon training data
- Cannot evaluate Pokemon similarity
- Missing entire game coverage

**Recommendations**:
1. Populate with Pokemon deck data
2. Target 1000+ decks minimum
3. Include card names, types, and metadata

### 4. Scryfall Card Database (`data/processed/scryfall_card_db.json`)

**Status**: ❌ **EMPTY**

- **Size**: 4KB (empty dict `{}`)
- **Expected**: Full MTG card database with metadata

**Impact**:
- Cannot resolve card names
- Cannot access card metadata (type, mana cost, text, etc.)
- Limits similarity features (functional similarity, type matching)

**Recommendations**:
1. Populate with Scryfall bulk data
2. Include essential fields: name, type, mana_cost, oracle_text, keywords
3. Consider compression or database format for large dataset

### 5. Raw Data (`data/raw/`)

**Status**: ✅ **PARTIALLY AVAILABLE**

- **Full dataset**: 1.1MB in `data/raw/data-full/`
- **Compressed files**: 62 `.json.zst` files in `scryfall.com/` directory
- **Sample dataset**: Empty (`data/raw/data-sample/`)

**Structure**:
```
data/raw/data-full/
├── games/
└── scraper/
    ├── deckbox.org/
    ├── mtgtop8.com/
    └── scryfall.com/ (62 compressed files)
```

**Issues**:
- Sample dataset is empty (should be used for fast iteration)
- Unclear what's in compressed files
- No documentation of data format

**Recommendations**:
1. Document raw data format and structure
2. Populate sample dataset with subset of full data
3. Add data validation scripts
4. Document extraction/processing pipeline

## Data Quality Metrics

### Coverage

| Game | Ground Truth | Decks | Card DB | Status |
|------|-------------|-------|---------|--------|
| MTG | 5 queries | Unknown | Empty | ⚠️ Partial |
| Pokemon | 0 queries | 0 decks | Unknown | ❌ Missing |
| Yu-Gi-Oh | 0 queries | 20 decks | Unknown | ⚠️ Partial |

### Completeness

- **Ground Truth**: 5/100+ needed (5%)
- **Deck Datasets**: 20/1000+ needed (2%)
- **Card Databases**: 0/3 needed (0%)

## Critical Issues Summary

1. **Ground truth too small**: 5 queries cannot support reliable evaluation
2. **Empty datasets**: Pokemon decks and Scryfall DB are empty
3. **Format inconsistency**: Yu-Gi-Oh uses numeric IDs instead of names
4. **No cross-game evaluation**: Only MTG has ground truth
5. **Missing metadata**: No documentation of data sources, dates, or processing

## Recommendations by Priority

### Priority 1: Critical (Blocks Evaluation)

1. **Expand ground truth dataset**
   - Target: 50-100 queries per game
   - Include all three games (MTG, Pokemon, Yu-Gi-Oh)
   - Add metadata (source, annotation method, date)

2. **Populate Scryfall card database**
   - Download Scryfall bulk data
   - Extract essential fields
   - Store in accessible format

3. **Fix Yu-Gi-Oh card name mapping**
   - Create ID → name mapping
   - Update deck dataset with card names
   - Or provide mapping file

### Priority 2: Important (Limits Training)

4. **Populate Pokemon deck dataset**
   - Scrape or download Pokemon deck data
   - Target 1000+ decks
   - Include card names and metadata

5. **Expand Yu-Gi-Oh deck dataset**
   - Increase from 20 to 1000+ decks
   - Ensure card name mapping

6. **Document raw data structure**
   - Document compressed file format
   - Add extraction scripts
   - Create sample dataset

### Priority 3: Enhancement (Improves Quality)

7. **Add data validation scripts**
   - Check for duplicates
   - Validate schema
   - Report statistics

8. **Add data versioning**
   - Track dataset versions
   - Document changes
   - Maintain changelog

9. **Create data quality dashboard**
   - Coverage metrics
   - Completeness scores
   - Update frequency

## Statistical Validity Concerns

With only 5 ground truth queries:

- **Cannot compute confidence intervals**: n=5 is too small
- **Cannot detect improvements**: Changes in P@10 could be noise
- **Cannot validate across games**: Only MTG has ground truth
- **Cannot measure signal quality**: Individual signal performance needs more queries

**Minimum requirements for statistical validity**:
- 30+ queries for basic evaluation (95% CI width ~0.15)
- 50+ queries for reliable evaluation (95% CI width ~0.10)
- 100+ queries for publication-quality evaluation (95% CI width ~0.07)

## Next Steps

1. **Immediate**: Document current dataset limitations in evaluation code
2. **Short-term**: Expand ground truth to 50+ queries (all games)
3. **Medium-term**: Populate missing datasets (Pokemon, Scryfall DB)
4. **Long-term**: Establish data quality pipeline and validation

## Related Documentation

- `DATA_ANALYSIS_AND_IMPROVEMENTS.md`: Mentions need for test set analysis
- `data/DATA_LAYOUT.md`: Documents expected structure
- `data/README.md`: Documents data directory organization
