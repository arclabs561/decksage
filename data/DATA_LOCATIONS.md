# Data Locations Summary

## Canonical Data: `src/backend/data-full/`

**This is the primary/canonical dataset** (3.8GB, 270K files)

### Structure:
```
src/backend/data-full/games/
├── magic/
│   ├── mtgtop8/collections/     56,548 decks
│   ├── goldfish/collections/   23,993 decks  
│   ├── deckbox/collections/     2,551 decks
│   └── scryfall/cards/         35,393 cards
├── pokemon/
│   ├── limitless-web/           1,208 decks ✅ (exported)
│   └── pokemontcg-data/cards/  19,817 cards
└── yugioh/
    ├── ygoprodeck/cards/        ~13K cards
    └── ygoprodeck-tournament/     794 decks ✅ (exported)
```

**Total Decks Available:**
- Magic: ~83,092 decks (56K + 24K + 2.5K)
- Pokemon: 1,208 decks
- Yu-Gi-Oh: 794 decks

## Cache: `.cache/blob/`

**Temporary HTTP cache** (104KB)
- Purpose: Caches HTTP responses during scraping
- Can be cleared/rebuilt
- Not canonical data

## Processed: `data/processed/`

**Exported/transformed data for ML** (generated from canonical)
- `decks_pokemon.jsonl`: 1,208 decks ✅
- `pairs_large.csv`: 7.5M pairs
- Other processed datasets

## Legacy: `data/raw/`

**Sample/legacy data** (116MB)
- May be outdated
- Check timestamps before using

## Summary

✅ **Canonical**: `src/backend/data-full/` - Never delete
📦 **Cache**: `.cache/blob/` - Can clear
📁 **Processed**: `data/processed/` - Regenerated from canonical
⚠️ **Legacy**: `data/raw/` - May be outdated

## Export Status

✅ Pokemon decks: Exported (1,208)
✅ Yu-Gi-Oh decks: Exported (794)
⏳ Magic decks: Not yet exported (83K+ available)
