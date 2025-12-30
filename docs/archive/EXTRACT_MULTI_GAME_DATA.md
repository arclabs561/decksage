# Extract Multi-Game Data

**Status**: Only MTG data available. Need to extract Pokemon and Yu-Gi-Oh! data.

---

## Current Status

- ✅ **MTG**: 53,478 decks exported (complete)
- ❌ **Pokemon**: 0 decks (need to extract)
- ❌ **Yu-Gi-Oh!**: 0 decks (need to extract)

---

## Extraction Commands

### Pokemon Tournament Decks
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract pokemon/limitless-web \
  --limit 2000
```

**Expected**: 1,208+ tournament decks

### Yu-Gi-Oh! Tournament Decks
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract yugioh/ygoprodeck-tournament \
  --scroll-limit 50 \
  --limit 5000
```

**Expected**: 520+ tournament decks (can scale to 5,000+)

### Yu-Gi-Oh! Cards (optional, for completeness)
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract yugioh/ygoprodeck \
  --section cards
```

**Expected**: 13,930 cards

### Pokemon Cards (optional, for completeness)
```bash
cd src/backend
go run cmd/dataset/main.go \
  --bucket file://./data-full \
  extract pokemon/pokemontcg-data \
  --limit 25000
```

**Expected**: 19,653 cards

---

## Using Makefile (Recommended)

The Makefile has convenient targets:

```bash
# Extract all games in parallel
make extract-all

# Or individually:
make extract-pokemon      # Pokemon cards
make extract-pokemon-web  # Pokemon tournament decks
make extract-ygo         # Yu-Gi-Oh! cards + tournament decks
```

---

## After Extraction

1. **Verify data**:
   ```bash
   find data-full/games/pokemon -name "*.zst" | wc -l
   find data-full/games/yugioh -name "*.zst" | wc -l
   ```

2. **Re-run multi-game export**:
   ```bash
   ./bin/export-multi-game-graph data-full/games data/processed/pairs_multi_game.csv
   ```

3. **Expected output**: All three games in the graph

---

## Storage Location

Data will be stored in:
- `data-full/games/pokemon/limitless-web/` (tournament decks)
- `data-full/games/yugioh/ygoprodeck-tournament/` (tournament decks)

The export command will find all `.zst` files recursively.

---

## Time Estimates

- **Pokemon**: ~10-20 minutes (1,208 decks)
- **Yu-Gi-Oh!**: ~15-30 minutes (520+ decks, can scale)
- **Total**: ~30-50 minutes for both

---

**Next Step**: Run extraction commands to get Pokemon and Yu-Gi-Oh! data!

