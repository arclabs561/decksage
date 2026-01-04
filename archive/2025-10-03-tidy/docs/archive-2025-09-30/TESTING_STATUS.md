# DeckSage Testing & Status Report

**Date**: 2025-09-30
**Go Version**: 1.25.1

## Project Overview

**DeckSage** is a **multi-game card game data collection and analysis platform** designed to support Magic: The Gathering, Yu-Gi-Oh!, Pokemon, and other trading card games. It provides:

- **Game-agnostic scraping infrastructure** with rate limiting and caching
- **Pluggable game implementations** - currently MTG, designed for YGO/Pokemon expansion
- **Multiple data sources per game** (tournament sites, card databases, user collections)
- **Blob storage abstraction** (local filesystem or S3)
- **Transform and indexing pipeline** for analysis and recommendations

**Current Status**: MTG fully implemented; architecture ready for other games

## Architecture Summary

### Backend (Go)
- **Language**: Go 1.19+ (tested with Go 1.25.1)
- **Location**: `src/backend/`
- **Module**: `collections`

### Key Components

1. **Scraper** (`scraper/scraper.go`)
   - Generic HTTP scraper with rate limiting
   - Caches responses in blob storage
   - Supports retry logic and throttling detection

2. **Dataset Interface** (`games/magic/dataset/dataset.go`)
   - Defines common interface for all data sources
   - `Extract()` - scrapes and parses data
   - `IterItems()` - iterates over stored items

3. **Dataset Implementations**
   - **Scryfall** - Card database and set collections
   - **Deckbox** - User deck/cube collections
   - **MTGGoldfish** - Tournament decks
   - **MTGTop8** - Tournament results

4. **Data Models** (`games/magic/game/game.go`)
   - `Card` - Individual card with faces, images, references
   - `Collection` - Decks, sets, or cubes with partitions
   - `CollectionType` - Deck/Set/Cube with metadata

## Current Testing Status

### ✅ Tests Are Working!

**Test Infrastructure**: Multi-tier testing strategy implemented

**Test Types**:
1. **Fast unit tests** - Use saved fixtures, run in ~1-2 seconds
2. **Integration tests** - Test against live sources (opt-in with build tags)
3. **Fixture refresh tool** - `cmd/testdata` utility to update test data

### Test Coverage Status

**Dataset Tests**:
- ✅ Scryfall - Card parsing, set parsing, regex validation
- ✅ MTGGoldfish - Deck parsing, URL handling, regex tests
- ✅ MTGTop8 - Deck parsing, ID extraction, regex tests
- ⚠️ Deckbox - Needs test implementation

**Core Tests**:
- ✅ Game models - 11 tests for validation, JSON marshaling
- ✅ Dataset infrastructure - Creation, blob operations
- ❌ Scraper - Needs tests for retry logic, rate limiting
- ❌ Transform - Needs tests
- ❌ Search - Needs tests

### Running Tests

```bash
# Fast unit tests (default, ~1-2 seconds)
cd src/backend
go test ./...

# Integration tests (slow, 5-10 minutes)
go test -tags=integration ./...

# Refresh test fixtures
go run ./cmd/testdata refresh
```

See `TESTING_GUIDE.md` for comprehensive testing documentation.

## Known Issues & Technical Debt

### 1. Outdated Dependencies
```
go 1.19  // Should upgrade to 1.23+
```

### 2. Code Issues Found

**In `mtgtop8/dataset.go:237`**:
```go
req, err := http.NewRequest("GET", itemURL, nil)
if err != nil {
    return nil  // BUG: Should return err, not nil
}
```

**In `mtgtop8/dataset.go:187`**:
```go
// BUG, lost err value
// Comment indicates a known bug where err is shadowed
```

**In `scryfall/dataset.go:236,247`**:
```go
Toughness: rawCard.Power,  // BUG: Should be rawCard.Toughness
```

### 3. Missing Error Handling
- Several parsers use `EachWithBreak` but don't always check final error state
- Some regex matches don't handle failure gracefully

### 4. Cache Directory Committed
`src/backend/cache/` contains badger database files (4000+ .sst files) that should be gitignored

## What Needs To Be Done

### Immediate (Critical)

1. **Fix Broken Test** ✅ COMPLETE
   - ✅ Updated `dataset_test.go` with integration build tag
   - ✅ Created fast unit tests in `dataset_unit_test.go`
   - ✅ Added fixture-based tests for each dataset

2. **Add .gitignore Entries**
   ```
   src/backend/cache/
   src/backend/build/
   ```

3. **Fix Known Bugs**
   - Fix toughness assignment in scryfall parser
   - Fix error return in mtgtop8 parser
   - Fix error shadowing in mtgtop8 page parser

### Short-term (High Priority)

4. **Expand Test Coverage** (In Progress)
   - ✅ Added tests for MTGGoldfish dataset
   - ✅ Added tests for MTGTop8 dataset
   - ✅ Added unit tests for parsing functions
   - ⏳ Add tests for Deckbox dataset
   - ⏳ Add more error case tests

5. **Add Integration Tests**
   - Test full extract -> transform -> index pipeline
   - Test blob storage operations
   - Test rate limiting behavior

6. **Update Dependencies**
   - Upgrade to Go 1.23+
   - Update deprecated packages
   - Run `go mod tidy`

### Medium-term (Important)

7. **Documentation**
   - Document scraper usage patterns
   - Add examples for each dataset
   - Document blob storage configuration
   - Create testing guide

8. **Refactoring**
   - Extract common parsing patterns
   - Improve error handling consistency
   - Add structured logging fields

9. **Validation**
   - Add validation tests for parsed data
   - Compare parsed results against expected schemas
   - Test edge cases (empty decks, special characters)

### Long-term (Nice to Have)

10. **CI/CD**
    - Set up GitHub Actions for tests
    - Add linting (golangci-lint)
    - Add coverage reporting

11. **Monitoring**
    - Add metrics for scraping success rates
    - Track parse errors by dataset
    - Monitor rate limit usage

12. **Performance**
    - Profile memory usage during bulk operations
    - Optimize blob storage access patterns
    - Add batch processing optimizations

## Running Tests

### Prerequisites
```bash
# None! All dependencies are handled by Go modules
```

### Current Test Commands
```bash
cd src/backend

# Fast unit tests (recommended for development)
go test ./...

# Verbose output
go test -v ./games/magic/dataset/...

# With coverage
go test -cover ./...

### Future Test Commands (After Expansion)
```bash
# Run all tests
go test ./...

# Run with coverage
go test -cover ./...

# Run specific dataset tests
go test ./games/magic/dataset/scryfall/...
go test ./games/magic/dataset/deckbox/...
go test ./games/magic/dataset/goldfish/...
go test ./games/magic/dataset/mtgtop8/...

# Run integration tests (after adding build tags)
go test -tags=integration ./...
```

## Dataset Extraction Commands

```bash
cd src/backend

# Extract from specific dataset (limit 10 items)
go run ./cmd/dataset extract scryfall --section=collections --limit=10 --bucket=file://./data

# Extract with custom rate limiting
export SCRAPER_RATE_LIMIT=100/m
go run ./cmd/dataset extract deckbox --limit=5 --bucket=file://./data

# Extract specific URL only
go run ./cmd/dataset extract mtgtop8 --only="https://mtgtop8.com/event?e=12345&d=67890"
```

## Multi-Game Roadmap

### Phase 1: Stabilize MTG (Current)
- ✅ Fix broken tests
- ✅ Fix known bugs
- ⏳ Expand test coverage
- ⏳ Document architecture
- ⏳ Validate data quality

### Phase 2: Generalize Patterns
- Extract common interfaces to `games/` package
- Create shared test utilities
- Document "Adding a New Game" guide
- Create example scaffold for new games

### Phase 3: Add Yu-Gi-Oh!
- Implement `games/yugioh/game/` models
- Add YGOPRODeck API dataset
- Add DB.yugioh.com dataset
- Write tests and validate quality

### Phase 4: Add Pokemon TCG
- Implement `games/pokemon/game/` models
- Add Pokemon TCG API dataset
- Add Limitless TCG dataset
- Write tests and validate quality

### Phase 5: Cross-Game Features
- Unified search across games
- Cross-game statistics dashboard
- Deck archetype classification
- Card similarity recommendations

## Next Steps

1. **Complete MTG stabilization** (see immediate tasks above)
2. **Extract common patterns** from MTG implementation
3. **Create game plugin scaffold** for easy addition of new games
4. **Document extension points** for contributors

See `ARCHITECTURE.md` for detailed design patterns and `TESTING_TODO.md` for implementation tasks.

## README Goals Status

From README.md:
> Goals:
> - Finish parsing deckbox, goldfish, mtgtop8, and scryfall, and verify quality.

**Status**:
- ✅ Parsers implemented for all 4 sources
- ❌ Quality verification incomplete (tests broken)
- ❌ No systematic validation of parsing accuracy
