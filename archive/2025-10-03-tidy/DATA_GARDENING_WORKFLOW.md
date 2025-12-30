# Data Gardening Workflow

## Philosophy

> "A dataset is not a static artifact - it's a living garden that requires continuous care, cultivation, and thoughtful growth."

## Current Garden Health

**Status**: 99.9/100 - Excellent ✅
- 4,718 decks
- 100% format metadata
- 99.8% archetype metadata
- Zero decks to prune
- 78.1% with sideboards

## Gardening Tools Built

### 1. Health Assessment (`data_gardening.py`)
**Purpose**: Check overall dataset health

**Metrics**:
- Metadata coverage
- Deck composition stats
- Issue identification
- Format/archetype distribution
- Overall health score

**Usage**:
```bash
cd src/ml
uv run python data_gardening.py
```

### 2. Expansion Planning (`dataset_expansion_plan.py`)
**Purpose**: Identify gaps and plan growth

**Identifies**:
- 436 underrepresented archetypes
- 374 critical targets (1-9 decks)
- Format balance issues
- Strategic priorities

**Output**: `data/scraping_targets.json` (targeted collection list)

### 3. Working Analysis Tools

Already built and validated:
- `archetype_staples.py` - Composition analysis
- `sideboard_analysis.py` - Strategic patterns
- `card_companions.py` - Co-occurrence patterns
- `deck_composition_stats.py` - Structure analysis

## Gardening Workflow

### Weekly: Health Check
```bash
# 1. Assess health
python data_gardening.py

# 2. Check for issues
# Review pruning list (if any)

# 3. Monitor metrics
# Track health score over time
```

### Monthly: Strategic Growth
```bash
# 1. Identify gaps
python dataset_expansion_plan.py

# 2. Target scraping
# Configure scraper for critical targets
# Run batch collection

# 3. Validate new data
python data_gardening.py  # Re-check health

# 4. Enrich with annotations
# LLM annotations for new high-value data
```

### Quarterly: Quality Cultivation
```bash
# 1. Deep quality review
# Manual review of sample decks
# Check annotation quality

# 2. Remove dead growth
# Prune outdated/invalid decks
# Clean inconsistencies

# 3. Enrich garden
# Add LLM annotations
# Add expert labels
# Cross-reference with external sources
```

## Expansion Strategy

### Phase 1: Critical Gaps (Now)
**Target**: 374 archetypes with 1-9 decks each
**Goal**: Get each to 20+ decks (minimum viable sample)
**Effort**: ~65 hours of targeted scraping
**Priority**: Top 50 most underrepresented

### Phase 2: Moderate Gaps (Next)
**Target**: 62 archetypes with 10-19 decks
**Goal**: Get each to 30+ decks (robust sample)
**Effort**: ~6 hours of opportunistic scraping
**Priority**: Collect during general scraping

### Phase 3: Format Balance (Later)
**Target**: Peasant, Vintage (underrepresented)
**Goal**: Balanced coverage across formats
**Effort**: General format-specific scraping
**Priority**: Ongoing maintenance

## Quality Principles

### Prune (Remove)
- Empty decks
- Corrupt data
- Duplicate entries
- Invalid format/archetype labels
- Extreme outliers (too small/large)

### Weed (Clean)
- Inconsistent naming
- Missing metadata
- Format violations
- Parsing errors

### Cultivate (Enrich)
- LLM annotations for context
- Expert labels for quality
- Archetype descriptions
- Card relationship annotations

### Grow (Expand)
- Target underrepresented archetypes
- Balance format distribution
- Strategic gap-filling
- Opportunistic broad collection

## Success Metrics

**Health Score**: 90+ (currently 99.9 ✅)
- Metadata coverage > 95%
- Issue rate < 5%
- Format balance coefficient > 0.7

**Coverage**:
- All major archetypes: 30+ decks ✅
- All formats: 200+ decks (mostly ✅)
- Total decks: 10,000+ (target, currently 4,718)

**Quality**:
- Manual review: 95%+ accurate
- LLM annotations: 1,000+ enriched decks
- Expert labels: 100+ validated queries

## Gardening Metaphors

**🌱 Seedling Stage** (1-9 decks)
- Fragile, needs attention
- Priority: Get to viable size
- Current: 374 archetypes

**🌿 Growing Stage** (10-29 decks)
- Establishing roots
- Priority: Support growth
- Current: 81 archetypes

**🌳 Mature Stage** (30+ decks)
- Healthy and productive
- Priority: Maintain quality
- Current: 227 archetypes

**🥀 Dead Growth** (To Prune)
- Corrupt or invalid data
- Priority: Remove
- Current: 0 decks ✅

## Next Session

1. Run targeted scraping for top 20 critical archetypes
2. Test LLM annotation on 10 sample decks
3. Validate new data quality
4. Re-assess garden health
5. Iterate based on results

## Philosophy Applied

"Data is not collected once and forgotten - it's cultivated over time, with care, intention, and respect for quality."

Like a garden:
- Plant strategically (target gaps)
- Water regularly (maintain health)
- Weed consistently (clean issues)
- Prune carefully (remove bad data)
- Harvest thoughtfully (use data well)
