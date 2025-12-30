# Data Directory

This directory contains all data artifacts for the DeckSage project.

## Structure

```
data/
├── raw/              # Scraped data from various sources
│   ├── data-full/    # Full dataset
│   └── data-sample/  # Sample dataset for testing
│
├── processed/        # Transformed data ready for ML
│   ├── pairs_large.csv          # Primary training data (7.5M pairs, MTG)
│   ├── pairs_multi_game.csv     # Multi-game pairs (24.6M pairs, currently MTG-only)
│   ├── card_attributes_enriched.csv  # Card attributes (27K cards)
│   ├── decks_pokemon.jsonl      # Pokemon decks (1,208)
│   ├── decks_all_unified.jsonl  # All decks unified (87K decks, raw export)
│   ├── decks_all_enhanced.jsonl # Enhanced decks (69K decks, normalized, deduplicated)
│   └── decks_all_final.jsonl    # Final decks (69K decks, ✅ RECOMMENDED for training)
│
├── decks/            # Per-game deck exports
│   ├── magic_*.jsonl            # Magic decks by source
│   ├── pokemon_*.jsonl          # Pokemon decks
│   └── yugioh_*.jsonl           # Yu-Gi-Oh decks
│
├── graphs/           # Graph edgelists for node2vec
│   └── *.edg         # Edge list files (gitignored)
│
├── embeddings/       # Trained embedding models
│   └── *.wv          # Word2Vec format embeddings (gitignored)
│
└── archive/          # Deprecated/old data
    ├── old-scraper-data/
    ├── frontend-old/
    └── *.json, *.csv  # Old artifacts
```

## Data Sources

### Raw Data
- **Scryfall**: MTG card database
- **MTGTop8**: Tournament decklists
- **MTGGoldfish**: Meta analysis
- **Deckbox**: Community decks

### Processed Data
- **pairs_large.csv**: Primary training data (7.5M pairs, 265 MB, MTG)
- **pairs_multi_game.csv**: Multi-game pairs (24.6M pairs, 1.6 GB, currently MTG-only)
- **card_attributes_enriched.csv**: Card attributes with functional tags (27K cards, 6 MB)
- **decks_all_final.jsonl**: ✅ **RECOMMENDED** - All decks enhanced (69K decks, 241 MB)
  - Normalized card names
  - Deduplicated by URL and card signature
  - Filtered invalid deck sizes
  - Source attribution backfilled
- **decks_all_unified.jsonl**: Raw unified export (87K decks, 292 MB, before enhancement)
- **decks_all_enhanced.jsonl**: Enhanced decks (69K decks, 241 MB, intermediate step)
- **decks_pokemon.jsonl**: Pokemon tournament decks (1,208 decks, 2.1 MB)

### Deck Exports
- **data/decks/**: Per-game and per-source deck exports
  - `magic_mtgtop8_decks.jsonl`: MTGTop8 tournament decks (56K+)
  - `pokemon_limitless_decks.jsonl`: Limitless TCG decks (1,208)
  - `yugioh_ygoprodeck_decks.jsonl`: YGOPRODeck tournament decks (794)

## Gitignore Policy

**Tracked** (committed to git):
- Small metadata files (JSON configs, READMEs)
- Small processed CSVs (<10MB)
- This README

**Ignored** (local only, synced to S3):
- `raw/` - Large scraped data
- `processed/pairs_multi_game.csv` - 1.5GB multi-game pairs
- `processed/pairs_large.csv` - 266MB large pairs
- `processed/decks_all_*.jsonl` - Large deck files (241-292MB)
- `decks/*.jsonl` - Large deck exports (94-147MB)
- `graphs/*.edg` - Generated graphs
- `graphs/node_features*.json` - Large graph node features (10MB+)
- `embeddings/*.wv` - Trained models
- `embeddings/*.pkl` - Pickled embeddings (39MB+)
- `embeddings/backups/*.wv` - Backup embeddings
- `archive/` - Deprecated files

**All large data files are synced to S3:** `s3://games-collections/`

## Usage

### Training Embeddings

**Co-occurrence training:**
```bash
cd src/ml
python card_similarity_pecan.py \
  --input ../../data/processed/pairs_large.csv \
  --output magic_128d
```

**Deck-based training:**
```bash
# Use enhanced final decks (recommended)
python train_with_decks.py \
  --input ../../data/processed/decks_all_final.jsonl \
  --output deck_based_128d
```

This will create:
- `data/graphs/magic_128d_graph.edg`
- `data/embeddings/magic_128d_pecanpy.wv`

### Loading Embeddings
```python
from gensim.models import KeyedVectors
wv = KeyedVectors.load('../../data/embeddings/magic_128d_pecanpy.wv')
similar = wv.most_similar('Lightning Bolt', topn=10)
```

## Data Sizes (Current)

- `raw/`: ~3.8GB (canonical storage in `src/backend/data-full/`)
- `processed/`: 
  - `pairs_large.csv`: 265 MB (7.5M pairs)
  - `pairs_multi_game.csv`: 1.6 GB (24.6M pairs)
  - `decks_all_final.jsonl`: 241 MB (69K decks) ✅
  - `card_attributes_enriched.csv`: 6 MB (27K cards)
- `graphs/`: ~3MB per graph
- `embeddings/`: ~1MB per model (22 files total)

## Data Pipeline

1. **Export**: `scripts/export_and_unify_all_decks.py` → `decks_all_unified.jsonl`
2. **Enhance**: `scripts/enhance_exported_decks.py` → `decks_all_enhanced.jsonl`
3. **Final**: `scripts/backfill_metadata.py` → `decks_all_final.jsonl` ✅

Use `decks_all_final.jsonl` for all deck-based training and analysis.








