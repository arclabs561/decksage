# Data Extraction Plan

**Date**: 2025-09-30

## Current Data Status

### Existing Data Discovered ✅

**Location**: `/old-scraper-data/`

| Source | Files Found | Status | Notes |
|--------|-------------|--------|-------|
| **www.mtggoldfish.com** | ~100+ deck files | ✅ Available | Compressed JSON+HTML |
| **deckbox.org** | Multiple files | ✅ Available | User decks/collections |
| **scryfall.com** | Set pages | ✅ Available | Set collections |
| **api.scryfall.com** | API responses | ✅ Available | Bulk data endpoints |
| **data.scryfall.io** | Downloaded data | ✅ Available | Card databases |

**Cache**: 213MB in `src/backend/cache/` (Badger DB, HTTP response cache)

### New Data Storage

**Target Location**: `src/backend/blob/` or custom directory

**Current Status**: Empty (no extracted data yet)

## Extraction Goals

### Phase 1: Sample Extraction (Start Small) 🎯

**Purpose**: Validate parsers with real data, test full pipeline

**Targets**:
1. **Scryfall** - 2-3 sets for card data
2. **MTGTop8** - 10-20 tournament decks
3. **Deckbox** - 10-20 user collections
4. **MTGGoldfish** - 10-20 tournament decks

**Timeline**: 5-10 minutes with rate limiting

**Command**:
```bash
cd src/backend

# Create data directory
mkdir -p ./data

# Extract samples (SAFE, small amounts)
export SCRAPER_RATE_LIMIT=100/m

# Scryfall sets (quick, has bulk data)
go run ./cmd/dataset extract scryfall \
  --section=collections \
  --limit=3 \
  --bucket=file://./data

# MTGTop8 decks (external site, respect rate limits)
go run ./cmd/dataset extract mtgtop8 \
  --limit=15 \
  --bucket=file://./data

# Deckbox user collections
go run ./cmd/dataset extract deckbox \
  --limit=15 \
  --bucket=file://./data

# MTGGoldfish decks (may need proxy or different approach)
# Skip for now due to 404/406 errors
```

**Expected Output**:
```
data/
├── magic/
│   ├── scryfall/
│   │   ├── collections/
│   │   │   ├── dmu.json    # Dominaria United
│   │   │   ├── bro.json    # Brothers' War
│   │   │   └── one.json    # Phyrexia: All Will Be One
│   ├── mtgtop8/
│   │   └── collections/
│   │       ├── 12345.67890.json
│   │       ├── 12346.67891.json
│   │       └── ... (15 decks)
│   └── deckbox/
│       └── collections/
│           ├── 3174326.json
│           └── ... (15 collections)
```

### Phase 2: Card Data (Larger, Controlled)

**Purpose**: Get comprehensive card database

**Target**: Scryfall card database (~50K cards)

**Approach**:
```bash
# This downloads ~500MB bulk data file
# Takes 2-5 minutes
go run ./cmd/dataset extract scryfall \
  --section=cards \
  --limit=1000 \  # Process first 1000 cards
  --bucket=file://./data
```

**Considerations**:
- Scryfall provides bulk download (respectful of their API)
- Single large download, then parse locally
- Can limit card processing for initial testing

### Phase 3: Use Existing Old Data

**Purpose**: Leverage already-scraped historical data

**Approach**:
1. Convert old scraper format to new blob storage format
2. Extract data from compressed files
3. Validate and import

**Script Needed**:
```bash
# Create converter tool
go run ./cmd/dataset import-old \
  --source=../../old-scraper-data/www.mtggoldfish.com \
  --target=file://./data \
  --limit=50
```

### Phase 4: Full Extraction (Production Scale)

**Purpose**: Build complete dataset for analysis

**Timeline**: Hours/days

**Targets**:
- All Scryfall cards (~50K)
- All Scryfall sets (~500)
- MTGTop8 recent decks (1000+)
- Deckbox popular collections (1000+)
- MTGGoldfish recent decks (500+)

## Data Types & Priorities

### 1. Official Collections (High Priority) ✅

**Scryfall Sets** - Official MTG sets released by Wizards
- Format: JSON collections with card lists
- Size: ~500 sets, ~50K unique cards
- Use Case: Card database, set completion tracking
- **Start with**: 3-5 recent sets

### 2. Tournament Decks (High Priority) ✅

**MTGTop8 Decks** - Competitive tournament results
- Format: HTML pages → JSON collections
- Size: Thousands of decks
- Use Case: Meta-game analysis, deck recommendations
- **Start with**: 15-20 recent decks

### 3. User Collections (Medium Priority) ✅

**Deckbox Collections** - User-created decks and cubes
- Format: HTML pages → JSON collections
- Size: Thousands of user collections
- Use Case: Deck ideas, card co-occurrence patterns
- **Start with**: 15-20 popular collections

### 4. Archetype Data (Medium Priority)

**MTGGoldfish Archetypes** - Grouped deck strategies
- Format: HTML pages → JSON collections
- Size: Hundreds of archetypes
- Use Case: Deck classification, archetype identification
- **Status**: ⚠️ Current URLs returning 404, needs investigation

## Execution Plan

### Step 1: Validate Existing Data ✅

```bash
# Check what's in old-scraper-data
cd /Users/henry/Documents/dev/decksage
find old-scraper-data -name "*.json.zst" | wc -l

# Check data quality
ls -lh old-scraper-data/www.mtggoldfish.com/deck/ | head -20
ls -lh old-scraper-data/deckbox.org/ | head -20
```

### Step 2: Small Sample Extraction (NOW)

```bash
cd src/backend

# Test infrastructure with minimal extraction
mkdir -p ./data-test

# Start with safest source (Scryfall)
export SCRAPER_RATE_LIMIT=100/m
go run ./cmd/dataset extract scryfall \
  --section=collections \
  --limit=2 \
  --bucket=file://./data-test \
  --log-level=info

# Verify output
ls -R ./data-test/

# If successful, try MTGTop8 (respecting rate limits)
go run ./cmd/dataset extract mtgtop8 \
  --limit=5 \
  --bucket=file://./data-test \
  --log-level=info
```

### Step 3: Verify Data Quality

```bash
# Check extracted files
find data-test -name "*.json" -exec wc -l {} \;

# Test parsing
go run ./cmd/dataset iterate \
  --dataset=scryfall \
  --bucket=file://./data-test \
  --limit=5

# Validate structure
jq '.' data-test/magic/scryfall/collections/*.json | head -50
```

### Step 4: Expand Gradually

Once Step 2 & 3 work:
```bash
# Increase limits gradually
go run ./cmd/dataset extract scryfall --limit=10 ...
go run ./cmd/dataset extract mtgtop8 --limit=20 ...
```

## Safety & Rate Limiting

### Rate Limits (Respectful Scraping)

```bash
# Conservative (recommended for external sites)
export SCRAPER_RATE_LIMIT=60/m   # 60 requests per minute

# Moderate (for testing)
export SCRAPER_RATE_LIMIT=100/m  # 100 requests per minute

# Aggressive (only for APIs that allow it)
export SCRAPER_RATE_LIMIT=300/m  # 300 requests per minute
```

### Proxy Usage (If Needed)

```bash
# If site blocks requests, use proxy
export HTTPS_PROXY=user:pass@proxy.example.com:7777
go run ./cmd/dataset extract mtgtop8 ...
```

### Caching

The scraper automatically caches responses:
- **Location**: `src/backend/cache/` (213MB existing)
- **Benefit**: Re-running extractions uses cache (fast, no new requests)
- **Control**: Use `--fetch-replace-all` to bypass cache

## Monitoring Extraction

### Watch Progress

```bash
# In separate terminal
watch -n 5 'find data -name "*.json" | wc -l'
```

### Check Logs

```bash
# Verbose logging
go run ./cmd/dataset extract scryfall \
  --log-level=debug \
  --limit=5 | tee extraction.log
```

### Verify Success

```bash
# Count files
find data -type f -name "*.json" | wc -l

# Check sizes
du -sh data/magic/*

# Sample files
find data -name "*.json" -print0 | xargs -0 ls -lh | head -10
```

## Expected Data Volumes

### Small Sample (Phase 1)
- **Size**: ~5-10 MB
- **Files**: ~30-50 JSON files
- **Time**: 5-10 minutes
- **Purpose**: Validation

### Medium Collection (Phase 2)
- **Size**: ~50-100 MB
- **Files**: ~200-500 JSON files
- **Time**: 30-60 minutes
- **Purpose**: Development & testing

### Full Dataset (Phase 4)
- **Size**: 1-5 GB
- **Files**: 10,000+ JSON files
- **Time**: Hours/days
- **Purpose**: Production analysis

## Next Actions (Prioritized)

### Immediate (Today)

1. ✅ Fix MTGGoldfish test fixture (DONE - used old data)
2. 🎯 **Run Phase 1 sample extraction** (NEXT)
   ```bash
   cd src/backend
   mkdir -p ./data-sample
   export SCRAPER_RATE_LIMIT=60/m
   go run ./cmd/dataset extract scryfall --section=collections --limit=2 --bucket=file://./data-sample
   go run ./cmd/dataset extract mtgtop8 --limit=5 --bucket=file://./data-sample
   ```
3. Verify extracted data quality
4. Document findings

### Short-term (This Week)

5. Create converter for old-scraper-data
6. Import existing data
7. Expand to Phase 2 (100+ files)
8. Build transform pipeline to process data

### Medium-term (This Month)

9. Full extraction (Phase 4)
10. Validate data quality across all sources
11. Build card co-occurrence matrices
12. Implement search/recommendations

## Success Criteria

✅ Phase 1 Complete when:
- [ ] 2-3 Scryfall sets extracted
- [ ] 15+ MTGTop8 decks extracted
- [ ] 15+ Deckbox collections extracted
- [ ] All files validate successfully
- [ ] No errors in logs
- [ ] Can iterate through extracted data

✅ Ready for Analysis when:
- [ ] 1000+ cards in database
- [ ] 100+ decks across sources
- [ ] Transform pipeline working
- [ ] Search index populated

## Notes

- **Respect robots.txt** and site policies
- **Use rate limiting** (60-100 req/min is safe)
- **Cache aggressively** to avoid redundant requests
- **Start small** to validate before scaling
- **Monitor logs** for errors or blocks
- **Use old data** where available (already scraped!)

---

**Ready to Start**: Phase 1 sample extraction
**Estimated Time**: 10-15 minutes
**Risk Level**: Low (small sample, cached responses available)
