# Test Fixtures Status

**Last Refreshed**: 2025-09-30

## Current Fixture Status

### ✅ Working with Real Data

| Dataset | Status | Files | Size | Notes |
|---------|--------|-------|------|-------|
| **MTGTop8** | ✅ Valid | 2 files | 182 KB | Real deck and search results |
| **Scryfall** | ✅ Valid | 2 files | 447 KB | Bulk data API + set page (DMU, 455 cards) |
| **MTGGoldfish** | ⚠️ 404 | 1 file | 19 lines | Needs valid deck URL |
| **Deckbox** | ❌ Empty | 0 files | - | Not yet refreshed |

### Test Results

```bash
$ go test ./games/magic/dataset/...
ok   collections/games/magic/dataset          0.785s
ok   collections/games/magic/dataset/goldfish 0.269s (1 skip)
ok   collections/games/magic/dataset/mtgtop8  0.277s
ok   collections/games/magic/dataset/scryfall 0.521s
```

**All tests passing!** ✅ (1 test skipped due to 404 fixture)

## Fixture Details

###  MTGTop8 Fixtures ✅

**Location**: `src/backend/games/magic/dataset/testdata/mtgtop8/`

**Files**:
- `deck_page.html` (39 KB) - Real tournament deck page
- `search_page.html` (143 KB) - Search results page

**Test Coverage**:
- ✅ Deck name extraction
- ✅ Format extraction
- ✅ Card parsing (2 sections: Main, Sideboard)
- ✅ ID regex validation

**Sample Data**: Successfully parsing real deck structure with card counts and sections.

### Scryfall Fixtures ✅

**Location**: `src/backend/games/magic/dataset/testdata/scryfall/`

**Files**:
- `bulk_data.json` (2.7 KB) - Bulk data API response with download URIs
- `set_page.html` (444 KB) - Dominaria United set page

**Test Coverage**:
- ✅ Bulk data API parsing
- ✅ Set name extraction: "Dominaria United (DMU)"
- ✅ Release date parsing: 2022-09-09
- ✅ Card grid parsing: 455 cards found
- ✅ Single-face card parsing
- ✅ Double-face card parsing
- ✅ Regex validation

**Sample Data**: Real set page with 455 cards, validates full parsing chain.

### MTGGoldfish Fixtures ⚠️

**Location**: `src/backend/games/magic/dataset/testdata/goldfish/`

**Status**: Contains 404 page (archetype URL no longer valid)

**Issue**: The archetype URL used in the refresh tool returned 404. Need to:
1. Find a stable deck/archetype URL
2. Update `cmd/testdata/main.go` with valid URL
3. Re-run: `go run ./cmd/testdata refresh --dataset=goldfish`

**Test Behavior**: Test gracefully skips when 404 detected.

### Deckbox Fixtures ❌

**Location**: `src/backend/games/magic/dataset/testdata/deckbox/`

**Status**: No fixtures yet

**To Refresh**:
```bash
cd src/backend
go run ./cmd/testdata refresh --dataset=deckbox
```

## Refreshing Fixtures

### Quick Commands

```bash
cd src/backend

# Refresh all working fixtures
go run ./cmd/testdata refresh --dataset=mtgtop8
go run ./cmd/testdata refresh --dataset=scryfall
go run ./cmd/testdata refresh --dataset=deckbox

# Or refresh all at once
go run ./cmd/testdata refresh
```

### What Gets Refreshed

Each dataset refresh fetches:

**MTGTop8**:
- One deck page from live tournament results
- One search results page

**Scryfall**:
- Bulk data API endpoint
- One set page (currently Dominaria United)

**MTGGoldfish**:
- One deck/archetype page (currently returns 404)

**Deckbox**:
- One deck/collection page

### Refresh Frequency

**Recommended**:
- Before major changes to parsers
- When tests start failing
- Monthly maintenance
- After website redesigns

**Not Needed**:
- For every test run (that's what fixtures are for!)
- During normal development
- For CI/CD (use fixtures checked into git)

## Validation Results

### Real Data Verification ✅

The fixtures contain actual HTML/JSON from live sources and successfully test:

1. **HTML Structure**: Correct CSS selectors and DOM traversal
2. **Data Extraction**: Regex patterns match real data
3. **Edge Cases**: Real world quirks (special characters, formatting)
4. **Complete Parsing**: Full deck/set/card parsing chains work

### What This Proves

✅ **Parsers work with real data** - Not just mocked/sanitized examples
✅ **Selectors are correct** - Finding actual elements in real HTML
✅ **Regex patterns match** - Working with live data formats
✅ **Integration works** - Full extract → parse → validate chain

## Next Steps

### Immediate

1. **Fix MTGGoldfish fixture**
   - Find valid deck URL (check recent decks on mtggoldfish.com)
   - Update `cmd/testdata/main.go`
   - Refresh: `go run ./cmd/testdata refresh --dataset=goldfish`

2. **Add Deckbox fixture**
   - Run: `go run ./cmd/testdata refresh --dataset=deckbox`
   - Verify test passes

### Ongoing

- Refresh fixtures quarterly
- Update when parsers change
- Check after website updates
- Keep fixtures small (single examples, not full datasets)

## Technical Notes

### Why Small Fixtures?

- **Fast tests**: Small files = quick parsing
- **Easy review**: Can inspect fixtures in IDE
- **Version control friendly**: Small diffs, easy to track changes
- **Sufficient coverage**: One example tests the full parsing logic

### Fixture Size Guidelines

- HTML pages: < 500 KB (single page)
- JSON responses: < 10 KB (minimal example)
- Total per dataset: < 1 MB

### Current Sizes

```
mtgtop8/   182 KB  ✅ Good
scryfall/  447 KB  ✅ Acceptable
goldfish/   19 B   ⚠️ 404 error
deckbox/     -     ❌ Missing
```

## Summary

**Status**: 🟡 **Mostly Working**

- ✅ 2/4 datasets have valid fixtures
- ✅ All tests passing (1 skip)
- ⚠️ 1 dataset needs fixture fix (goldfish)
- ❌ 1 dataset needs initial refresh (deckbox)

**Tests verify real-world data** from live sources, validating that parsers work with actual website HTML/JSON structures.

---

**To fix remaining issues**:
```bash
# 1. Fix MTGGoldfish URL in cmd/testdata/main.go
# 2. Run refreshes
cd src/backend
go run ./cmd/testdata refresh --dataset=goldfish
go run ./cmd/testdata refresh --dataset=deckbox
go test ./games/magic/dataset/...
```
