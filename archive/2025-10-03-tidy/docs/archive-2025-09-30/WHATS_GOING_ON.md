# DeckSage: What's Going On

**Last Updated**: 2025-09-30

## TL;DR

DeckSage is a **multi-game card game data collection and analysis platform**. The MTG implementation is functional with web scrapers for 4 major sources, but testing was broken and slow. **We just fixed that**.

## Project Status: 🟡 Active Development

### What Works ✅

1. **Data Collection Infrastructure**
   - Generic scraper with rate limiting and caching
   - Blob storage abstraction (local/S3)
   - 4 dataset sources for Magic: The Gathering:
     - **Scryfall** - Card database + set collections
     - **Deckbox** - User deck/cube collections
     - **MTGGoldfish** - Tournament decks
     - **MTGTop8** - Tournament results

2. **Data Models**
   - Card model with multi-face support
   - Collection model (Deck/Set/Cube)
   - JSON serialization and validation

3. **Testing (Newly Fixed!)**
   - Fast unit tests with fixtures (~1-2s)
   - Integration tests for live validation
   - Fixture refresh tooling
   - 20+ tests across packages

### What Needs Work 🚧

1. **Missing Tests**
   - Scraper retry/rate limiting logic
   - Transform pipeline
   - Search functionality
   - Deckbox dataset

2. **Known Bugs** (documented, not critical)
   - Toughness field bug in Scryfall parser (line 236)
   - Error handling issues in MTGTop8 parser
   - Cache directory shouldn't be committed

3. **Technical Debt**
   - Go 1.19 → should upgrade to 1.23+
   - Dependencies need updating
   - Some parsers need error handling improvements

## Architecture Overview

```
src/backend/
├── cmd/
│   ├── dataset/          # CLI for data extraction
│   └── testdata/         # Tool to refresh test fixtures
├── games/magic/
│   ├── game/            # Data models (Card, Collection)
│   ├── dataset/         # Dataset interface + implementations
│   │   ├── scryfall/    # Card database scraper
│   │   ├── deckbox/     # User collection scraper
│   │   ├── goldfish/    # Tournament deck scraper
│   │   ├── mtgtop8/     # Tournament results scraper
│   │   └── testdata/    # Test fixtures
├── scraper/             # Generic HTTP scraper
├── blob/                # Storage abstraction (local/S3)
├── transform/           # Data processing pipeline
└── search/              # Search/indexing (Meilisearch)
```

## How It Works

### 1. Extract Data

```bash
cd src/backend

# Scrape 10 decks from MTGTop8
go run ./cmd/dataset extract mtgtop8 --limit=10 --bucket=file://./data

# Scrape sets from Scryfall
go run ./cmd/dataset extract scryfall --section=collections --limit=5
```

The scraper:
- Makes HTTP requests with rate limiting
- Caches responses in blob storage
- Parses HTML/JSON into structured data
- Validates and stores as JSON

### 2. Transform (WIP)

Transform raw data into analysis-ready format:
- Normalize card names
- Build card co-occurrence matrices
- Extract deck archetypes

### 3. Index (WIP)

Index data for search and recommendations:
- Card similarity search
- Deck recommendation
- Meta-game analysis

## Recent Changes (Today!)

### Testing Infrastructure Overhaul

**Problem**: Tests were hitting live websites, taking 10+ minutes, and could fail due to network issues.

**Solution**: Implemented multi-tier testing:

1. **Fast Unit Tests** (default)
   - Use saved HTML/JSON fixtures
   - Run in ~1-2 seconds
   - No network calls
   - Great for development

2. **Integration Tests** (opt-in)
   - Use `//go:build integration` tag
   - Test against live sources
   - Run with: `go test -tags=integration`
   - For CI/pre-release validation

3. **Fixture Refresh Tool**
   - `go run ./cmd/testdata refresh`
   - Updates saved HTML from live sources
   - Keeps tests current

### Files Created/Modified

**New Files**:
- `games/magic/dataset/testdata/` - Fixture directory
- `games/magic/dataset/testdata/README.md` - Fixture docs
- `cmd/testdata/main.go` - Fixture refresh tool
- `games/magic/dataset/dataset_unit_test.go` - Fast unit tests
- `games/magic/dataset/scryfall/dataset_test.go` - Parser tests
- `games/magic/dataset/goldfish/dataset_test.go` - Parser tests
- `games/magic/dataset/mtgtop8/dataset_test.go` - Parser tests
- `TESTING_GUIDE.md` - Comprehensive testing docs
- `WHATS_GOING_ON.md` - This file

**Modified Files**:
- `games/magic/dataset/dataset_test.go` - Now integration test with build tag
- `TESTING_STATUS.md` - Updated status

## Quick Start

### Run Tests (Fast)

```bash
cd src/backend
go test ./...
```

**Expected**: All tests pass in ~1-2 seconds

### Run Integration Tests (Slow)

```bash
go test -tags=integration ./games/magic/dataset/ -v
```

**Expected**: Tests pass in 5-10 minutes (makes real HTTP requests)

### Scrape Data

```bash
cd src/backend

# Small test scrape
export SCRAPER_RATE_LIMIT=100/m
go run ./cmd/dataset extract mtgtop8 --limit=3 --bucket=file://./data

# Check what was scraped
ls -R ./data/magic/mtgtop8/
```

### Refresh Test Fixtures

```bash
cd src/backend
go run ./cmd/testdata refresh
```

## Multi-Game Vision

Currently **MTG-only**, but designed for expansion:

### Phase 1: MTG (Current)
- ✅ Infrastructure complete
- ✅ 4 data sources working
- ✅ Tests implemented
- 🚧 Quality validation needed

### Phase 2: Architecture Generalization
- Extract common patterns
- Create game plugin interface
- Document extension points

### Phase 3: Yu-Gi-Oh!
- YGOPRODeck API
- DB.yugioh.com scraper

### Phase 4: Pokemon TCG
- Pokemon TCG API
- Limitless TCG scraper

### Phase 5: Cross-Game Features
- Unified search
- Cross-game statistics
- Archetype classification

## Key Decisions Made

### Why Fixtures?

**Problem**: Tests were slow and unreliable

**Options Considered**:
1. Mock HTTP layer → Complex, loses confidence
2. Test only parsing → Misses integration issues
3. **Fixtures + Integration tags** → Best of both worlds ✓

**Result**: Fast development loop (1-2s tests) + confidence (integration tests on demand)

### Why Go?

- Fast performance for web scraping
- Great concurrency for parallel parsing
- Strong typing catches bugs early
- Excellent tooling (testing, profiling)

### Why Blob Abstraction?

- Start with local filesystem (simple)
- Scale to S3 (production)
- Same code works for both

## Common Tasks

### Add a New Dataset Source

1. Create `games/magic/dataset/newsource/dataset.go`
2. Implement `Dataset` interface (Extract, IterItems, Description)
3. Add tests with fixtures
4. Add to CLI in `cmd/dataset/main.go`

### Fix a Parser

1. Update the parsing code
2. Run tests: `go test ./games/magic/dataset/newsource/...`
3. If fixtures are stale: `go run ./cmd/testdata refresh --dataset=newsource`

### Debug Scraping

1. Enable verbose logging:
   ```go
   log.SetLevel("DEBUG")
   ```
2. Check cached responses:
   ```bash
   ls -R ~/.cache/decksage/  # or wherever blob storage is
   ```
3. Use `--fetch-replace-all` to bypass cache

## Resources

- `README.md` - Basic project overview
- `TESTING_GUIDE.md` - Complete testing documentation
- `TESTING_STATUS.md` - Detailed current status
- `ARCHITECTURE.md` - System design (if exists)
- `games/magic/dataset/testdata/README.md` - Fixture documentation

## Next Steps (Recommended Priority)

1. **Fix Known Bugs** (1-2 hours)
   - Scryfall toughness field
   - MTGTop8 error handling

2. **Add Deckbox Tests** (1 hour)
   - Create `deckbox/dataset_test.go`
   - Add fixtures

3. **Scrape Full Dataset** (hours/days)
   - Run full extraction for all sources
   - Validate data quality
   - Document edge cases

4. **Transform Pipeline** (days)
   - Design card co-occurrence format
   - Implement transform logic
   - Test with real data

5. **Search/Recommendations** (weeks)
   - Integrate Meilisearch
   - Card similarity algorithm
   - Deck recommendation engine

## Questions?

- Check `TESTING_GUIDE.md` for testing questions
- Check `TESTING_STATUS.md` for current status
- Check code comments for implementation details
- Look at existing dataset implementations as examples

## Summary

**DeckSage is a working prototype** with solid fundamentals. The data collection infrastructure is complete and tested. The next phase is validating data quality, fixing minor bugs, and building out the analysis/recommendation features.

The testing infrastructure is now **fast and reliable**, enabling confident development.
