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

## Data Lineage

All data follows the 7-order hierarchy (see `docs/LLM_LABELS_LINEAGE.md`):
- Order 0: Primary source data (S3/local, never git)
- Order 1+: Derived data (can be regenerated, stored local/S3)

## Best Practices

1. **Never commit data files** - Always use `.gitignore`
2. **Document data sources** - See `DATA_USAGE.md`
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
