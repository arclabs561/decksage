# Data Storage Strategy

## Git vs Local/S3 Storage

This repository follows a strict separation between:
- **Git**: Code, configuration, documentation (no copyrighted content)
- **Local/S3**: Data files, potentially copyrighted content, large files

## What Goes in Git

✅ **Safe to commit:**
- Source code (Python, Go, Rust, TypeScript)
- Configuration files (`.toml`, `.yaml`, `.json` configs)
- Documentation (`.md` files)
- Test code (but not test data with copyrighted content)
- Build scripts and tooling

## What Goes in Local/S3 Only

❌ **Never commit to git:**
- Card data files (even minimal metadata)
- Card text (oracle text, flavor text)
- Card artwork or images
- Font files
- Large data files (>100KB generally)
- Potentially copyrighted content
- Training data
- Embeddings
- Database files

### Local Storage

Store locally in:
- `data/processed/` - Processed card data
- `data/graphs/` - Graph data
- `data/embeddings/` - Embedding files
- `data/raw/` - Raw scraped data

### S3 Storage

Sync to S3 for:
- Backup and sharing
- Cloud training
- Team collaboration

**S3 Bucket**: `s3://games-collections/`

**Sync commands:**
```bash
# Sync to S3
s5cmd sync data/processed/ s3://games-collections/processed/
s5cmd sync data/graphs/ s3://games-collections/graphs/
s5cmd sync data/embeddings/ s3://games-collections/embeddings/

# Sync from S3
s5cmd sync s3://games-collections/processed/ data/processed/
```

## Questionable Content

The following are stored locally/S3 only (not in git):

### Card Data Files
- `data/processed/card_attributes_minimal.csv` - Card names and metadata
- `data/processed/scryfall_card_db.json` - Magic card database
- `data/processed/ground_truth_v1.json` - Ground truth data
- `src/ml/scryfall_card_db.json` - ML card database

### Test Fixtures
- `src/ml/tests/fixtures/decks_*.jsonl` - Test deck data
- `experiments/downstream_tests/*.jsonl` - Evaluation data

**Why?** Even minimal card data (names, types) could be considered questionable.
Better to keep it local/S3 and document the data sources and usage.

## Data Usage and Copyright Information

### What Data Is Stored

This repository stores only **metadata** about trading cards, not copyrighted content:

#### Stored (Low Risk)
- **Card names** - Factual data, generally not copyrightable
- **Card types** - Factual classifications (e.g., "Creature", "Instant")
- **Mana costs** - Factual data (e.g., "{R}", "{1}{B}")
- **Colors** - Factual data (e.g., "Red", "Blue")
- **Rarity** - Factual data (e.g., "Common", "Rare")
- **Deck lists** - Public tournament data (card names and counts only)

#### NOT Stored (Copyrighted Content)
- ❌ **Card text** (oracle text, flavor text) - Copyrighted by game publishers
- ❌ **Card artwork** - Copyrighted by game publishers/artists
- ❌ **Card images** - Copyrighted by game publishers/artists
- ❌ **Game rules text** - Copyrighted by game publishers

### Data Sources

#### Scryfall API
- **Source**: https://scryfall.com/docs/api
- **Data**: Magic: The Gathering card metadata
- **Terms**: Public API, allows data use per their terms of service
- **What we use**: Card names, types, mana costs, colors, rarity
- **What we don't use**: Oracle text, flavor text, images

#### Pokemon TCG API
- **Source**: https://pokemontcg.io/
- **Data**: Pokemon Trading Card Game metadata
- **Terms**: Public API, allows data use per their terms of service
- **What we use**: Card names, types, HP, energy costs
- **What we don't use**: Attack text, ability text, images

#### Tournament Deck Lists
- **Source**: Public tournament sites (MTGGoldfish, etc.)
- **Data**: Public tournament deck lists
- **What we use**: Card names and counts only
- **What we don't use**: Player names, event details beyond format/archetype

### Backend Code

The backend code (`src/backend/games/*/dataset/*.go`) extracts data from APIs, including
fields for card text. However:

- **Card text fields are extracted but NOT stored** in tracked data files
- Only metadata fields are persisted to disk
- Card text extraction exists for API compatibility but is discarded

### Legal Considerations

#### Card Names
Card names are factual data and are generally not subject to copyright protection
under US copyright law (facts cannot be copyrighted).

#### Card Text
Card text (oracle text, flavor text) is creative expression and is copyrighted
by game publishers. This project does not store card text.

#### Card Artwork
Card artwork is copyrighted by game publishers and/or individual artists.
This project does not store any card artwork or images.

#### Game Mechanics
Game mechanics may be protected by patents, but the mechanics themselves are
not stored - only metadata about which cards exist and their factual properties.

#### Fair Use
This project is intended for research and educational purposes. The use of factual
metadata (card names, types) for research/analysis purposes may qualify as fair use,
but commercial use may require appropriate licensing.

### Trademarks

- **Magic: The Gathering** is a trademark of Wizards of the Coast LLC
- **Pokemon** is a trademark of Nintendo, Creatures Inc., and Game Freak Inc.
- This project is not affiliated with, endorsed by, or sponsored by these companies

## Data Lineage

All data follows the 7-order hierarchy (see `docs/llm-labels-lineage.md`):
- Order 0: Primary source data (S3/local, never git)
- Order 1+: Derived data (can be regenerated, stored local/S3)

## Best Practices

1. **Never commit data files** - Always use `.gitignore`
2. **Document data sources** - See data sources section above
3. **Use S3 for sharing** - Sync important data to S3
4. **Keep git clean** - Only code and documentation
5. **Document storage** - Where data lives (local vs S3)

## Migration Notes

Files previously tracked in git have been removed:
- Card data files moved to `.gitignore`
- Assets directory removed (fonts, symbols)
- Large data files already excluded

These files should be:
1. Stored locally in `data/` directories
2. Synced to S3 for backup/sharing
3. Never committed to git

## Questions or Concerns

If you have questions about data usage or copyright concerns, please open an issue
or contact the project maintainers.
