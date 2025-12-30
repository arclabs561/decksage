# Scraping Expansion Plan

## Current State
- **4,718 decks** (MTGTop8 only)
- Formats: Modern (900), Pauper (844), cEDH (600), Legacy (596), Standard (501), Pioneer (318)
- Date range: Recent (exact range unknown)

## Target: 20K+ Decks

### New Sources

#### 1. MTGTop8 - Expand Depth ⚡
**Current**: Unknown page count  
**Target**: Last 12 months, all formats

```bash
cd src/backend
go run cmd/dataset/main.go extract magic/mtgtop8 --pages 500 --formats all
```

**Expected yield**: +5,000 decks  
**Effort**: Low (scraper exists)  
**Priority**: **HIGH** - Easy wins

---

#### 2. MTGGoldfish - Tournament Decks 🐠
**Status**: Parser exists but not heavily used  
**Target**: Modern, Pioneer, Standard metagame decks

```bash
go run cmd/dataset/main.go extract magic/goldfish --limit 2000
```

**Expected yield**: +3,000 decks  
**Effort**: Medium (test existing scraper)  
**Priority**: **HIGH**

---

#### 3. MTGO League Results 🎮
**Source**: https://www.mtgo.com/decklists  
**Data**: 5-0 league decks (competitive, recent)

**New scraper needed**:
```go
// src/backend/games/magic/dataset/mtgo/dataset.go
type Dataset struct {
    // Parse MTGO league 5-0 dumps
    // Format: Plain text decklists
}
```

**Expected yield**: +5,000 decks  
**Effort**: High (new scraper)  
**Priority**: **MEDIUM** - High quality data

---

#### 4. Archidekt - Community Decks 🏗️
**Source**: https://archidekt.com/api/  
**Data**: User-created decks with tags

**Considerations**:
- Mix of casual and competitive
- Need quality filtering
- Has API (easier than scraping)

**Expected yield**: +10,000 decks (but lower quality)  
**Effort**: Medium (API available)  
**Priority**: **LOW** - Quality concerns

---

#### 5. Moxfield - Modern Data 📊
**Source**: https://www.moxfield.com/  
**Data**: Tournament imports, user decks

**Expected yield**: +3,000 competitive decks  
**Effort**: Medium  
**Priority**: **MEDIUM**

---

### Data Quality Tiers

**Tier 1: Tournament Results** (Priority scraping)
- MTGTop8 (✅ have)
- MTGGoldfish tournaments (✅ have scraper)
- MTGO 5-0 leagues (❌ need scraper)
- SCG results (❌ need scraper)
- Channel Fireball events (❌ need scraper)

**Tier 2: Metagame Decks**
- MTGGoldfish meta decks
- Moxfield tournament imports
- MTGAZone Arena decks

**Tier 3: Community Decks** (Lower priority)
- Archidekt
- TappedOut
- Deckstats.net

**Strategy**: Focus on Tier 1, sample from Tier 2, skip Tier 3 initially

---

## Implementation Plan

### Week 1: Expand Existing Sources
```bash
# 1. MTGTop8 - go deeper
go run cmd/dataset/main.go extract magic/mtgtop8 \
  --pages 500 \
  --start-date 2024-01-01

# 2. MTGGoldfish - full extract
go run cmd/dataset/main.go extract magic/goldfish \
  --limit 3000 \
  --formats Modern,Pioneer,Standard,Legacy

# Expected: +8,000 decks
```

### Week 2: MTGO Scraper
```go
// Implement src/backend/games/magic/dataset/mtgo/
// Parse https://www.mtgo.com/en/mtgo/decklists

type MTGODataset struct {
    // Daily 5-0 dumps
    // Format: Plain text
}

func (d *MTGODataset) ParseLeagueResult(html []byte) (*Deck, error)
```

**Expected**: +5,000 decks from recent leagues

### Week 3: Quality Validation
```python
# Run LLM validator on new data
python llm_data_validator.py --new-decks-only

# Filter low quality
python filter_quality.py --min-score 0.8
```

### Week 4: Integration
- Merge all sources
- Deduplicate
- Export unified dataset
- Run expanded experiments

---

## Rate Limiting & Ethics

### Respectful Scraping
```go
// Default rate limits per source
MTGTop8:    1 req/second
MTGGoldfish: 1 req/2 seconds
MTGO:       1 req/second
```

### Caching Strategy
```go
// Cache all HTTP responses
// Never re-scrape same URL
// Store in blob:// with timestamps
```

### User-Agent
```
DeckSage/0.1 (Research Project; contact@example.com)
```

---

## Expected Dataset After Expansion

### Size
- **Current**: 4,718 decks
- **After expansion**: 20,000+ decks
- **Growth**: 4.2x

### Coverage
| Format | Current | Target |
|--------|---------|--------|
| Modern | 900 | 3,000 |
| Pauper | 844 | 2,000 |
| Legacy | 596 | 1,500 |
| Pioneer | 318 | 1,500 |
| Standard | 501 | 2,000 |
| cEDH | 600 | 2,000 |
| Vintage | 232 | 500 |
| Other | 727 | 1,500 |

### Temporal Coverage
- **Current**: Unknown range
- **Target**: Last 12 months minimum
- **Goal**: Track meta evolution

---

## Quick Wins (This Week)

```bash
# 1. Check current scraper capacity
cd src/backend
go run cmd/dataset/main.go index magic/mtgtop8 | wc -l

# 2. Scrape more pages from existing sources
go run cmd/dataset/main.go extract magic/mtgtop8 --pages 200

# 3. Test MTGGoldfish scraper
go run cmd/dataset/main.go extract magic/goldfish --limit 100

# 4. Export and validate
go run cmd/export-hetero/main.go data-full/games/magic/mtgtop8/collections \
  decks_expanded.jsonl

# 5. Run quality check
python llm_data_validator.py
```

**Expected outcome**: 10K decks by end of week

---

## Monitoring

### Scraping Dashboard
```python
# Track progress
{
  "mtgtop8": {
    "last_run": "2025-10-02",
    "decks_scraped": 4718,
    "success_rate": 0.98,
    "avg_time": "1.2s/deck"
  },
  "goldfish": {
    "last_run": "2025-10-02", 
    "decks_scraped": 0,
    "status": "ready"
  }
}
```

### Quality Metrics
```python
# After each scraping batch
{
  "new_decks": 1000,
  "quality_score": 0.85,
  "duplicates_found": 12,
  "format_violations": 3,
  "action_needed": ["Review 3 illegal decks"]
}
```

---

## Cost & Resources

### Storage
- Current: ~100MB (4,718 decks compressed)
- After expansion: ~500MB (20K decks)
- Trivial storage cost

### Bandwidth
- Current: Cached, minimal
- Expansion: ~10GB download (one-time)
- Cost: Free

### Compute
- Scraping: Minutes to hours (depends on rate limits)
- LLM validation: ~$10-20 for full dataset
- Export/processing: Minutes

**Total cost**: < $25 for complete expansion

---

## Success Criteria

✅ **20K+ decks** from multiple sources  
✅ **Quality score > 0.85** on validation  
✅ **Temporal coverage**: 12+ months  
✅ **Format diversity**: All major formats  
✅ **Deduplication**: < 1% duplicates  

---

## Next Commands

```bash
# Start expansion now
cd /Users/henry/Documents/dev/decksage/src/backend

# 1. Check what we can scrape
go run cmd/dataset/main.go index magic/mtgtop8 --pages 100

# 2. Start scraping
go run cmd/dataset/main.go extract magic/mtgtop8 --pages 200

# 3. Monitor progress
watch -n 10 'find data-full/games/magic/mtgtop8/collections -name "*.zst" | wc -l'
```



