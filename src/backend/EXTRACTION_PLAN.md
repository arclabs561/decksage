# Data Extraction Plan - Fix Coverage & Diversity

**Goal**: Extract 200+ more decks with format balance and archetype diversity

## Current Problems

1. **Temporal**: All decks from same day (2025-09-30 extraction)
2. **Coverage**: Modern (16), Pioneer (15), Vintage (20) under-represented
3. **Clustering**: All Modern decks from same tournament event
4. **Diversity**: Some archetypes over-represented (Pauper Faeries 18.9%)

## Extraction Strategy

### Phase 1: Modern Expansion (Priority 1)

**Target**: 50 Modern decks (currently 16)

**Strategy**:
```bash
# Extract from MTGTop8 browse pages
go run ./cmd/dataset extract mtgtop8 \
  --limit=50 \
  --bucket=file://./data-full

# Or extract specific Modern tournaments
go run ./cmd/dataset extract mtgtop8 \
  --section="modern" \
  --limit=100 \
  --bucket=file://./data-full
```

**Archetypes to target**:
- Burn (missing entirely)
- Jund/BGx (Tarmogoyf decks)
- Death's Shadow
- Amulet Titan
- Living End
- Hammer Time
- Yawgmoth Combo
- Rhinos/Crashing Footfalls
- Tron variants

### Phase 2: Pauper Diversification (Priority 2)

**Target**: 30 more Pauper decks (currently 37, need balance)

**Avoid**: More Faeries (already 18.9%)

**Target archetypes**:
- Tron (Urzatron) - more copies
- Affinity
- Bogles
- Elves - more copies
- Red Deck Wins - already have some
- Walls Combo
- Moggwarts

### Phase 3: Other Formats (Priority 3)

**Pioneer**: 15 → 30 decks  
**Vintage**: 20 → 30 decks  
**Peasant**: 2 → 10 decks (if possible)

### Phase 4: Temporal Diversity (Future)

**Extract historical decks**:
- 2024 Q1, Q2, Q3, Q4
- 2023 Q1-Q4
- Track meta evolution

## Commands

### Extract More MTGTop8 Decks

```bash
cd src/backend

# Large extraction
export SCRAPER_RATE_LIMIT=100/m
go run ./cmd/dataset extract mtgtop8 \
  --limit=200 \
  --bucket=file://./data-full

# Check what we got
go run ./cmd/analyze-decks data-full/games/magic
```

### Re-export Clean Graph

```bash
# After extraction
go run ./cmd/export-decks-only data-full/games/magic pairs_decks_v2.csv
```

### Re-train Embeddings

```bash
cd ../ml
.venv/bin/python card_similarity_pecan.py \
  --input ../backend/pairs_decks_v2.csv \
  --dim 128 \
  --walk-length 80 \
  --num-walks 10
```

## Success Metrics

- [ ] Modern: 50+ decks with 10+ unique archetypes
- [ ] Pauper: 60+ decks with archetype balance (<20% any one archetype)
- [ ] All formats: 30+ decks minimum
- [ ] Tarmogoyf, Ragavan present in embeddings
- [ ] Modern Burn archetype represented
- [ ] Temporal span: >6 months (if possible)

## Validation

After extraction:
1. Run analyze-decks to check diversity
2. Re-export graph (deck-only)
3. Re-train embeddings
4. Expert validation: Query Modern staples
5. Check format coverage: All formats >80%
