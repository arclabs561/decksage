# Next Steps for Dataset Expansion

## Executive Summary

Attempted dataset expansion on October 4, 2025. **Key finding**: MTGGoldfish parser is completely broken (0% success rate), preventing significant expansion. Quick wins available through Pokemon card completion and targeted MTGTop8 scraping.

## Immediate Actions (Choose One)

### Option 1: Quick Win - Complete Pokemon Cards (30 min, +7K cards)
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract pokemontcg \
  --parallel 8
```
**Value**: Complete Pokemon card coverage (3,000 → 10,000 cards)  
**Risk**: Low (parser working, syntax error already fixed)  
**Effort**: 30 minutes runtime

### Option 2: Fix MTGGoldfish Parser (2-3 hours, enables +2-5K decks)
```bash
# Step 1: Inspect current HTML structure
curl "https://www.mtggoldfish.com/deck/7248896" > /tmp/goldfish_sample.html
open /tmp/goldfish_sample.html  # or inspect in browser

# Step 2: Find parser code
cd src/backend/games/magic/dataset/goldfish
# Update parse logic to match current HTML structure

# Step 3: Test on single deck
go run ../../cmd/dataset/main.go \
  --bucket file://./data-full \
  extract goldfish \
  --limit 1 \
  --only https://www.mtggoldfish.com/deck/7248896

# Step 4: Scale gradually
go run ../../cmd/dataset/main.go \
  --bucket file://./data-full \
  extract goldfish \
  --limit 100
```
**Value**: Unlocks 2,000-5,000 decks + meta percentage data  
**Risk**: Medium (requires code changes, testing)  
**Effort**: 2-3 hours development

### Option 3: Targeted MTGTop8 Format Expansion (+200-500 decks, 1 hour)
```bash
cd src/backend

# Target under-represented formats
# Pioneer (currently 15 decks → target 100)
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract mtgtop8 \
  --section pioneer \
  --limit 100

# Vintage (currently 20 decks → target 100)
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract mtgtop8 \
  --section vintage \
  --limit 100

# Modern (different page range to avoid cache hits)
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract mtgtop8 \
  --section modern \
  --start 500 \
  --pages 100
```
**Value**: Better format balance, 200-500 new decks  
**Risk**: Low (scraper working)  
**Effort**: 1 hour runtime

## Medium-Term Actions (Next 2 Weeks)

### Implement Limitless TCG API (Pokemon Tournament Decks)

**Prerequisites**:
1. Request API key: https://play.limitlesstcg.com/account/settings/api
   - Fill out form with project name "DeckSage"
   - Wait 1-3 days for approval
2. Receive API key

**Implementation** (once key received):
```bash
# Create new dataset implementation
src/backend/games/pokemon/dataset/limitless/dataset.go

# Key endpoints:
# GET https://play.limitlesstcg.com/api/tournaments?game=PTCG&limit=100
# GET https://play.limitlesstcg.com/api/tournaments/{id}/standings
```

**Structure**:
```go
type LimitlessDataset struct {
    log  *logger.Logger
    blob *blob.Bucket
    apiKey string // from env var LIMITLESS_API_KEY
}

func (d *LimitlessDataset) Extract(ctx context.Context, sc *scraper.Scraper, options ...games.UpdateOption) error {
    // 1. Fetch tournament list
    // 2. For each tournament, fetch standings (includes decklists)
    // 3. Store as CollectionTypeDeck with metadata:
    //    - player, placing, record (wins/losses/ties)
    //    - tournament name, date, player count
    //    - deck archetype (auto-assigned by Limitless)
}
```

**Expected Yield**: 500-1,000 Pokemon tournament decks  
**Effort**: 1-2 days development + testing

### Implement YGOPRODeck Tournament Scraper

**Strategy**:
```bash
# Option A: Check for API
curl "https://db.ygoprodeck.com/api/v7/deckinfo.php?deck_id=651815"
# If API exists, use it (easier)

# Option B: HTML scraping
# Target: https://ygoprodeck.com/category/format/tournament%20meta%20decks
# Parse listing pages → extract deck URLs → parse individual decks
```

**Implementation Location**:
```
src/backend/games/yugioh/dataset/ygoprodeck-tournament/dataset.go
```

**Data to Extract**:
- Deck name (e.g., "Yummy")
- Tournament name + date (e.g., "YCS Lima, Sep 27 2025")
- Placement (e.g., "Top 16", "Winner")
- Player name
- Player count
- Main deck, Extra deck, Side deck (card IDs from image URLs)

**Expected Yield**: 200-500 Yu-Gi-Oh tournament decks  
**Effort**: 2-3 days development + testing

## Recommended Sequence

**Week 1** (Oct 4-11):
1. **Day 1** (Today): Complete Pokemon cards ✅ (30 min)
2. **Day 2-3**: Fix MTGGoldfish parser (2-3 hours)
3. **Day 4**: Scale MGoldfish scraping (+2,000 decks)
4. **Day 5**: Targeted MTGTop8 expansion (+300 decks, format balance)
5. **Day 5**: Submit Limitless TCG API key request

**Week 2** (Oct 12-18):
1. **Day 8-9**: Implement Limitless TCG scraper (once API key approved)
2. **Day 10-12**: Implement YGOPRODeck tournament scraper
3. **Day 13**: Test + validate all new scrapers
4. **Day 14**: Run full expansion (Pokemon + YGO tournament decks)

## Success Metrics

**By End of Week 1**:
- Pokemon: 10,000 cards ✅ (complete)
- MTG: 57,000-58,000 decks (better format balance)
- MGoldfish parser: Fixed and tested

**By End of Week 2**:
- Pokemon: 10,000 cards + 500 tournament decks
- YGO: 13,930 cards + 200 tournament decks
- MTG: 58,000+ decks
- Cross-game parity: All games have tournament deck coverage

## Technical Considerations

### Parser Health Monitoring
Add logging to track parser success rates:
```go
// After each batch of scraping
successRate := float64(parsedDecks) / float64(attemptedDecks)
log.Infof("Parser success rate: %.2f%% (%d/%d)", successRate*100, parsedDecks, attemptedDecks)

// Alert if < 50%
if successRate < 0.5 {
    log.Warnf("⚠️  Parser success rate below 50% - HTML structure may have changed")
}
```

### Testing Strategy
Before scaling any scraper:
1. Test on 1 item → verify parsing works
2. Test on 10 items → check edge cases
3. Test on 100 items → measure success rate
4. Scale to 1,000+ if success rate > 90%

### Rate Limiting
Current: 100 requests/minute (default)
- Sufficient for MTGTop8, Scryfall, Pokemon TCG API
- May need adjustment for large-scale scraping
- Configure via `SCRAPER_RATE_LIMIT` env var

## Command Reference

### Check Current Data Counts
```bash
# MTG decks
fd -e zst . src/backend/data-full/games/magic/mtgtop8/collections -t f | wc -l

# Pokemon cards
fd -e zst . src/backend/data-full/games/games/pokemon/pokemontcg/cards -t f | wc -l

# YGO cards
fd -e zst . src/backend/data-full/games/games/yugioh/ygoprodeck/cards -t f | wc -l
```

### Export Data
```bash
cd src/backend

# Export MTG decks with metadata
go run cmd/export-hetero/main.go \
  data-full/games/magic/mtgtop8/collections \
  ../../data/mtg_decks_expanded.jsonl

# Export card graph for training
go run cmd/export-graph/main.go pairs.csv
```

### Validate Data Quality
```bash
cd src/ml

# Run data validator
uv run python llm_data_validator.py

# Check deck health metrics
uv run python data_gardening.py
```

## Risk Assessment

| Action | Risk | Mitigation |
|--------|------|------------|
| Complete Pokemon cards | Low | Parser already working, syntax fixed |
| Fix MTGGoldfish parser | Medium | Test on small sample first, have rollback plan |
| Targeted MTGTop8 scraping | Low | Known working scraper, just different sections |
| Limitless TCG API | Low | Well-documented API, just need key approval |
| YGOPRODeck scraper | Medium | HTML parsing, may need browser emulation |

## Questions to Resolve

1. **API Key Status**: Have you already requested a Limitless TCG API key?
2. **Priority**: Which matters more - more MTG decks or cross-game parity (Pokemon/YGO)?
3. **MTGGoldfish**: Worth fixing or skip and focus on other sources?
4. **Timeline**: Urgent need or can take 2 weeks for full implementation?

---

**Recommended Next Command**:
```bash
# Highest ROI, lowest risk, quickest win
cd src/backend && go run cmd/dataset/main.go --bucket file://./data-full extract pokemontcg --parallel 8
```

This gets us to 10,000 Pokemon cards in 30 minutes, completing one game's card coverage.
