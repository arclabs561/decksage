# Multi-Game Data Status

**Date**: 2025-12-04
**Current State**: Only MTG data available in S3

---

## Current Data

### ✅ Magic: The Gathering
- **S3**: `s3://games-collections/games/magic/`
- **Downloaded**: 53,482 files (210MB)
- **Exported**: 53,478 decks, 24.6M edges
- **Status**: Complete

### ❌ Pokemon TCG
- **S3**: Not found
- **Expected Sources**:
  - Limitless TCG: 1,208+ tournament decks
  - Pokemon TCG Data (GitHub): 19,653 cards
- **Status**: Need to extract/scrape

### ❌ Yu-Gi-Oh!
- **S3**: Not found
- **Expected Sources**:
  - YGOPRODeck Tournament: 520+ tournament decks
  - YGOPRODeck API: 13,930 cards
- **Status**: Need to extract/scrape

---

## Data Extraction Commands

### Pokemon Tournament Decks
```bash
cd src/backend
go run cmd/dataset/main.go extract pokemon/limitless-web --limit 2000
```

### Yu-Gi-Oh Tournament Decks
```bash
cd src/backend
go run cmd/dataset/main.go extract yugioh/ygoprodeck-tournament --scroll-limit 50
```

### Yu-Gi-Oh Cards
```bash
cd src/backend
go run cmd/dataset/main.go extract yugioh/ygoprodeck --section cards
```

### Pokemon Cards
```bash
cd src/backend
go run cmd/dataset/main.go extract pokemon/pokemontcg-data
```

---

## Expected Yields

| Game | Tournament Decks | Cards | Source |
|------|------------------|-------|--------|
| MTG | 53,478 ✅ | 35,400+ | MTGTop8, Scryfall |
| Pokemon | 1,208+ ⏳ | 19,653 | Limitless TCG |
| Yu-Gi-Oh! | 520+ ⏳ | 13,930 | YGOPRODeck |

---

## Next Steps

1. **Extract Pokemon data** using `limitless-web` dataset
2. **Extract Yu-Gi-Oh! data** using `ygoprodeck-tournament` dataset
3. **Upload to S3** (or use local `data-full` directory)
4. **Re-run multi-game export** with all three games
5. **Train unified embeddings** on complete multi-game graph

---

## Storage Options

### Option 1: Local `data-full` Directory
- Extract directly to `data-full/games/pokemon/` and `data-full/games/yugioh/`
- Run export from local directory
- No S3 upload needed

### Option 2: S3 Storage
- Extract to local, then upload to S3
- Use `s5cmd cp` for fast uploads
- Run export from S3 (requires S3 download first)

**Recommendation**: Use local `data-full` directory for now, upload to S3 later if needed.
