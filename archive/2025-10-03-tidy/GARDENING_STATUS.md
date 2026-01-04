# Data Gardening Status - October 3, 2025

## Garden Health: 99.9/100 ✅

**Current Dataset**:
- 4,718 decks with metadata
- 100% format coverage
- 99.8% archetype coverage
- Zero bad data to prune
- Thriving garden!

**Source Breakdown**:
- MTGTop8: 4,718 decks (primary source)
- Deckbox: 2,029 decks (available, not yet integrated)
- Goldfish: Ready to scrape
- Scryfall: 35,400 cards (metadata source)

## Tools Built

### Analysis Tools (All Working) ✅
1. **archetype_staples.py** - Find cards in 70%+ of archetype decks
2. **sideboard_analysis.py** - What people sideboard
3. **card_companions.py** - What cards appear together
4. **deck_composition_stats.py** - Deck structure patterns

### Gardening Tools ✅
5. **data_gardening.py** - Health assessment (99.9/100)
6. **dataset_expansion_plan.py** - Gap analysis (436 targets identified)
7. **test_annotation_batch.py** - LLM annotation testing

## Expansion Opportunities

**Current**: 4,718 MTGTop8 decks
**Available**: 2,029 Deckbox decks (scraped, not integrated)
**Targets**: 436 underrepresented archetypes

**Quick Wins**:
1. Integrate Deckbox data → +2,029 decks immediately
2. Scrape Goldfish → +500-1,000 decks
3. Expand MTGTop8 → Fill specific archetype gaps

**Strategic Gaps** (need 20+ decks each):
- 374 archetypes with 1-9 decks (critical)
- 62 archetypes with 10-19 decks (moderate)
- Pioneer, Peasant formats underrepresented

## Annotation Status

**LLM Testing**: ✅ Working
- Tested on 5 sample decks
- Detected archetype mismatches
- Identified deck quality issues
- API functional, costs reasonable (~$0.50 per 100 decks)

**Next**: Scale to 100 decks for quality validation

## Immediate Actions

### 1. Integrate Deckbox Data (Instant Growth)
```bash
cd src/backend
# Deckbox data already scraped, just needs export
go run cmd/export-hetero/main.go data-full/games/magic/deckbox/collections decks_deckbox.jsonl
cat decks_deckbox.jsonl >> ../../data/processed/decks_with_metadata.jsonl
# Garden grows: 4,718 → 6,747 decks (+43%)
```

### 2. Expand Goldfish (Targeted Growth)
```bash
# Start with small batch to test
go run cmd/dataset/main.go extract goldfish --bucket=file://./data-full --limit=100

# Export and integrate
go run cmd/export-hetero/main.go data-full/games/magic/goldfish/collections decks_goldfish.jsonl
cat decks_goldfish.jsonl >> ../../data/processed/decks_with_metadata.jsonl
```

### 3. Test Annotation at Scale
```bash
cd ../ml
# Annotate 100 diverse decks
uv run python annotate_batch_100.py
# Cost: ~$0.50-1.00
# Time: 5-10 minutes
```

### 4. Re-assess Health
```bash
uv run python data_gardening.py
# Check if health stays >95 after growth
```

## Growth Milestones

**Milestone 1** (Today): Integrate existing data
- Target: 6,747 decks (+43%)
- Effort: 10 minutes
- Result: Broader coverage immediately

**Milestone 2** (This Week): Fill critical gaps
- Target: 8,000+ decks
- Effort: Targeted scraping for top 50 archetypes
- Result: Minimum viable samples for critical archetypes

**Milestone 3** (This Month): Rich annotations
- Target: 1,000+ annotated decks
- Effort: LLM annotation in batches
- Result: Quality labels for training/validation

**Milestone 4** (Next Month): Mature garden
- Target: 10,000+ decks, all well-represented
- Effort: Continuous cultivation
- Result: Production-ready dataset

## Gardening Principles Applied

**Plant strategically**: Target gaps, don't collect blindly
**Water regularly**: Monitor health continuously
**Weed consistently**: Remove bad data (currently zero)
**Prune carefully**: Keep quality high (99.9/100)
**Harvest thoughtfully**: Build useful tools

## Next Commands to Run

```bash
# 1. Quick win - integrate Deckbox
cd /Users/henry/Documents/dev/decksage/src/backend
go run cmd/export-hetero/main.go data-full/games/magic/deckbox/collections ../../data/processed/decks_deckbox.jsonl

# 2. Combine datasets
cd ../../data/processed
cat decks_deckbox.jsonl >> decks_with_metadata.jsonl

# 3. Re-assess health
cd ../../src/ml
uv run python data_gardening.py

# 4. Test expanded tools
uv run python archetype_staples.py
# Should now show even better coverage
```

## Philosophy

"A dataset is a garden. It grows through care, not just collection. We cultivate quality, prune waste, and harvest insights."

The garden is already healthy (99.9/100). Now we grow it strategically.
