# Dataset Expansion Plan - October 4, 2025

## Current State

| Game | Cards | Tournament Decks | Status |
|------|-------|------------------|--------|
| **MTG** | 35,400 (Scryfall) ✅ | 55,293 (MTGTop8) ✅ | Production |
| **Pokemon** | ~3,000 (incomplete) ⚠️ | 0 ❌ | Incomplete |
| **Yu-Gi-Oh** | 13,930 (YGOPRODeck) ✅ | 0 ❌ | Cards only |

## Expansion Strategy

### Phase 1: Immediate Expansion (Today)

**MTGTop8 Deep Scrape** - 5,000+ more decks
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract mtgtop8 \
  --pages 200 \
  --parallel 32
```

**Expected yield**: +5,000 MTG tournament decks
**Time estimate**: 30-45 minutes with rate limiting
**Risk**: Low (scraper working, tested)

**MTGGoldfish Debug** - Fix failing scraper
- Issue: Dataset name mismatch
- Expected yield: +1,000-2,000 decks
- Provides meta percentage data
- Status: Needs debugging

### Phase 2: Pokemon Tournament Decks (Next 2-3 days)

**Limitless TCG API Integration**

**API Details**:
- Base URL: `https://play.limitlesstcg.com/api`
- Auth: API key required (request at https://play.limitlesstcg.com/account/settings/api)
- Endpoints:
  - `GET /tournaments?game=PTCG&limit=100` - List tournaments
  - `GET /tournaments/{id}/standings` - Get decklists with full metadata

**Data Structure**:
```json
{
  "player": "espel",
  "name": "Tsubasa Shimizu",
  "country": "JP",
  "placing": 1,
  "record": {"wins": 13, "losses": 2, "ties": 0},
  "decklist": { /* game-specific format */ },
  "deck": {
    "id": "lost-zone-box",
    "name": "Lost Zone Box",
    "icons": ["comfey", "sableye"]
  }
}
```

**Implementation Steps**:
1. ✅ Request API key from Limitless TCG
2. Create `src/backend/games/pokemon/dataset/limitless/dataset.go`
3. Implement tournament listing + standings scraper
4. Store as `CollectionTypeDeck` with Pokemon-specific metadata
5. Test with 10-20 tournaments first
6. Scale to 100+ tournaments

**Expected yield**: 500-1,000 Pokemon tournament decks
**Metadata richness**: Player, placement, record, tournament info, deck archetype

### Phase 3: Yu-Gi-Oh Tournament Decks (Next week)

**YGOPRODeck Tournament Scraper**

**Source**: `https://ygoprodeck.com/category/format/tournament%20meta%20decks`

**Data Available**:
- Deck name (e.g., "Yummy")
- Tournament (e.g., "YCS Lima")
- Placement (e.g., "Top 16", "Winner")
- Player name
- Date
- Player count
- Main deck, Extra deck, Side deck (card IDs in image URLs)

**Example deck page**: `https://ygoprodeck.com/deck/yummy-651815`

**Implementation Strategy**:
1. Scrape category listing page (paginated)
2. Extract deck URLs from "Tournament Meta Decks" category
3. Parse individual deck pages for:
   - Tournament metadata (name, date, placement)
   - Player info
   - Card lists (from image URLs: `images/cards/{CARD_ID}.jpg`)
4. Store as `CollectionTypeDeck` with Yu-Gi-Oh metadata

**Challenges**:
- HTML parsing (not API-based)
- May need browser emulation for JS-rendered content
- Card lists extracted from image URLs

**Expected yield**: 200-500 Yu-Gi-Oh tournament decks
**Metadata richness**: Player, tournament, placement, deck archetype

**Alternative**: Check if YGOPRODeck has an API endpoint
```bash
# Test for API
curl https://db.ygoprodeck.com/api/v7/deckinfo.php?deck_id=651815
```

### Phase 4: Pokemon Card Completion (This week)

**Fix Pokemon TCG API Pagination**

**Status**: Scraper is correct, pagination error at page 13 is gracefully handled
**Action**: Re-run scraper to completion

```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract pokemontcg \
  --parallel 8
```

**Expected yield**: ~10,000 complete Pokemon cards (from current ~3,000)
**Time estimate**: 15-20 minutes

### Phase 5: Data Quality & Enrichment (Ongoing)

**MTG Deck Metadata Enhancement**
- Extract player names from MTGTop8 pages
- Extract tournament name/date
- Extract placement/rank
- Add event type (GP, SCG, MTGO, etc.)

**LLM Annotations**
- Expand test sets (Pokemon: 10→30, YGO: 13→30)
- Run LLM annotations on expanded data
- Validate quality metrics

**Temporal Diversity**
- Extract historical MTGTop8 data (2023-2024)
- Track meta evolution over time

## Priority Ranking

**P0 - This Week**:
1. ✅ MTGTop8 deep scrape (+5,000 decks)
2. Pokemon card completion (+7,000 cards)
3. Request Limitless TCG API key

**P1 - Next 2 Weeks**:
1. Implement Limitless TCG scraper (Pokemon decks)
2. Implement YGOPRODeck tournament scraper (YGO decks)
3. Debug MTGGoldfish scraper

**P2 - Next Month**:
1. MTG deck metadata enhancement
2. Temporal diversity (historical decks)
3. Test set expansion + LLM annotations

## Success Metrics

**3-Month Targets**:
- MTG: 60,000+ tournament decks
- Pokemon: 10,000+ cards, 500+ tournament decks
- Yu-Gi-Oh: 13,930 cards ✅, 200+ tournament decks
- All games: Test sets with 30+ queries each
- Cross-game parity: All games have tournament deck coverage

**Data Quality**:
- Deck health: >95/100 across all games
- Metadata completeness: 80%+ decks with player/event/placement
- Temporal span: 12+ months of data
- Format diversity: All major formats represented

## Technical Requirements

### Limitless TCG API
- **Blocker**: API key required (manual approval)
- **Action**: Submit request form today
- **Approval time**: 1-3 days typically

### YGOPRODeck Scraper
- **Requirement**: HTML parsing (goquery)
- **Complexity**: Medium (structured HTML)
- **Alternative**: Check for undocumented API

### Browser Emulation
- **Status**: Not currently needed
- **Re-evaluate**: Only if high-value targets require JS execution

## Rollout Strategy

1. **Conservative first** (+200 decks) → validate quality
2. **Scale incrementally** (+1,000 decks) → monitor health
3. **Full expansion** (+5,000 decks) → production scale
4. **Continuous monitoring** - data quality dashboard

## Commands Ready to Run

```bash
# Immediate MTGTop8 expansion
./scripts/expand_scraping.sh quick  # +2K decks
./scripts/expand_scraping.sh full   # +10K decks

# Pokemon cards completion
cd src/backend
go run cmd/dataset/main.go --bucket file://./data-full extract pokemontcg

# Validate data quality after expansion
cd src/ml
uv run python llm_data_validator.py

# Export expanded dataset
cd src/backend
go run cmd/export-hetero/main.go data-full/games/magic/mtgtop8/collections ../../data/expanded_decks.jsonl
```

## Notes

- All scrapers respect rate limits (100/min default)
- HTTP caching prevents duplicate fetches
- Graceful error handling for pagination
- Resume capability for interrupted scrapes
- Blob storage with zstd compression

## Next Actions

1. Run MTGTop8 expansion now
2. Complete Pokemon cards scraping
3. Submit Limitless TCG API key request
4. Create YGOPRODeck scraper prototype
5. Validate expanded data quality
