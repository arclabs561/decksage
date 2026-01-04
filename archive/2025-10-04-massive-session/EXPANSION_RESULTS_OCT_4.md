# Dataset Expansion Results - October 4, 2025

## Expansion Attempt Summary

Ran `./scripts/expand_scraping.sh quick` with goals:
1. MTGTop8 expansion (+100 pages, ~2K decks expected)
2. MTGGoldfish test (100 decks)
3. Pokemon cards completion

## Results

### MTGTop8: Processed but No Net Gain ⚠️

**Pages Processed**: 100 pages at ~328 pages/second
**Items Parsed**: 2,475 items
**Current Total**: 55,293 decks (unchanged from before)

**Analysis**: The scraper successfully fetched and processed pages, but no new unique decks were added. This indicates:
- HTTP cache hit on previously scraped URLs (good - no duplicate fetches)
- Pages contained decks already in database
- Need to scrape **different** pages/sections, not re-scrape same Modern section

**Next Action**: Target specific under-represented formats:
```bash
# Target Pioneer specifically
go run cmd/dataset/main.go --bucket file://./data-full extract mtgtop8 --section pioneer --pages 50

# Target Vintage
go run cmd/dataset/main.go --bucket file://./data-full extract mtgtop8 --section vintage --pages 50
```

### MTGGoldfish: Parser Completely Broken ❌

**Issue**: Parser extracting 0 cards from every deck page
**Error Pattern**: `failed to parse collection: collection is invalid: partition Main has no cards`
**Decks Attempted**: 6,000+ URLs
**Success Rate**: 0%

**Root Cause**: MTGGoldfish likely changed their HTML structure and our parser no longer works

**Next Actions**:
1. Inspect a sample MTGGoldfish deck page HTML
2. Update parser to match current page structure
3. Test on 10 decks before scaling

**Sample Command to Debug**:
```bash
# Fetch and inspect a single deck
curl "https://www.mtggoldfish.com/deck/7248896" > /tmp/goldfish_sample.html

# Try parsing with verbose logs
go run cmd/dataset/main.go --bucket file://./data-full extract goldfish --limit 1 --only https://www.mtggoldfish.com/deck/7248896
```

### Pokemon Cards: Not Reached ⚠️

Script was canceled before Pokemon card scraping phase due to time.

**Status**: Still at ~3,000 cards (incomplete)
**Next Action**: Run independently:
```bash
cd src/backend
go run cmd/dataset/main.go --bucket file://./data-full extract pokemontcg --parallel 8
```

## Key Findings

### 1. HTTP Caching Working Well ✅
- No duplicate fetches
- Respects existing cached pages
- Saves bandwidth and time

### 2. MTGGoldfish Parser Broken ❌
- Zero cards extracted from 6,000+ deck pages
- Parser completely out of sync with current HTML
- Blocks expansion from this source

### 3. Need Targeted Scraping Strategy
- Re-scraping same sections yields no new data
- Need to target specific formats/archetypes
- Or scrape historical pages (older dates)

## Immediate Next Steps

### Priority 1: Fix MTGGoldfish Parser (1-2 hours)
1. Fetch sample deck HTML
2. Inspect current structure
3. Update parser code in `src/backend/games/magic/dataset/goldfish/`
4. Test on 10 decks
5. Scale to 100, then 1,000

**Value**: +2,000-5,000 decks with meta percentage data

### Priority 2: Complete Pokemon Cards (30 minutes)
```bash
cd src/backend
go run cmd/dataset/main.go --bucket file://./data-full extract pokemontcg --parallel 8
```

**Value**: +7,000 Pokemon cards (complete coverage)

### Priority 3: Targeted MTGTop8 Expansion (1 hour)
```bash
# Scrape under-represented formats
cd src/backend

# Pioneer (currently 15 decks)
go run cmd/dataset/main.go --bucket file://./data-full extract mtgtop8 --section pioneer --limit 50

# Vintage (currently 20 decks)
go run cmd/dataset/main.go --bucket file://./data-full extract mtgtop8 --section vintage --limit 50

# Modern (older tournaments - need different page ranges)
go run cmd/dataset/main.go --bucket file://./data-full extract mtgtop8 --section modern --start 500 --pages 100
```

**Value**: +200-500 decks with better format balance

### Priority 4: Implement New Tournament Scrapers (2-3 days)

**Limitless TCG API (Pokemon)**:
- Request API key: https://play.limitlesstcg.com/account/settings/api
- Implement scraper in `src/backend/games/pokemon/dataset/limitless/`
- Expected: 500-1,000 tournament decks

**YGOPRODeck Tournament Scraper**:
- Target: https://ygoprodeck.com/category/format/tournament%20meta%20decks
- HTML parsing required (or find API)
- Expected: 200-500 tournament decks

## Revised Expansion Estimate

| Source | Current | Immediate Gain | Medium-Term | Total Target |
|--------|---------|----------------|-------------|--------------|
| **MTGTop8** | 55,293 | +200-500 (targeted) | +2,000 (historical) | 58,000 |
| **MTGGoldfish** | 0 (broken) | +2,000 (fix parser) | +3,000 (scale) | 5,000 |
| **Pokemon Cards** | 3,000 | +7,000 (complete) | - | 10,000 |
| **Pokemon Decks** | 0 | - | +500 (Limitless API) | 500 |
| **YGO Decks** | 0 | - | +200 (scraper) | 200 |

**Total Immediate**: +9,200-9,500 items (mostly cards + some decks)
**Total 2-Week**: +12,700 items (includes Pokemon/YGO tournament decks)

## Technical Debt Identified

1. **MTGGoldfish parser maintenance** - needs regular updates when site changes
2. **No automated tests for parsers** - changes break silently
3. **No parser health monitoring** - didn't detect 0% success rate until manual inspection
4. **Section-specific scraping not well documented** - hard to target underrepresented formats

## Recommendations

### Short-term (This Week)
1. Fix MTGGoldfish parser - highest ROI
2. Complete Pokemon cards - easy win
3. Targeted MTGTop8 scraping - format balance

### Medium-term (Next 2 Weeks)
1. Implement Limitless TCG scraper
2. Implement YGOPRODeck scraper
3. Add parser health monitoring

### Long-term (Next Month)
1. Add automated parser tests
2. Historical MTGTop8 scraping (temporal diversity)
3. Additional MTG sources (MTGO, Arena data)
4. Data quality dashboard

## Lessons Learned

1. **Cache is both friend and foe** - prevents duplicate work but also prevents expansion if scraping same pages
2. **Parsers need maintenance** - websites change, parsers break silently
3. **Need targeted strategies** - random scraping hits diminishing returns quickly
4. **Cross-game parity matters** - MTG has 55K decks, Pokemon/YGO have 0 tournament decks
5. **Test parsers continuously** - 0% success rate went undetected during scrape

---

**Next Command to Run**:
```bash
# Complete Pokemon cards (30 min, high value)
cd src/backend && go run cmd/dataset/main.go --bucket file://./data-full extract pokemontcg --parallel 8
```
