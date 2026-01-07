# Data Directory Structure

This directory contains all processed data, embeddings, and cached artifacts.

## Directory Layout

```
data/
├── processed/          # Processed graph data (CSV, EDG files)
├── graphs/            # Graph edgelists for embeddings
├── embeddings/        # Trained embedding models (.wv, .kv)
├── raw/               # Raw extracted data (not tracked in git)
├── cache/             # Temporary cache (not tracked in git)
└── archive/           # Archived datasets
```

## File Types

- `.csv` - Card co-occurrence pairs (card1, card2, weight)
- `.edg` - Graph edgelists for Node2Vec training
- `.wv` - Gensim KeyedVectors (word2vec format embeddings)
- `.kv` - Gensim KeyedVectors (binary format)
- `.zst` - Zstandard compressed data (scraped decks/cards)
- `.attrs` - Metadata attributes for compressed blobs

## Data Flow

1. Scraping → `raw/` (or `src/backend/data-full/`)
2. Transform → `processed/*.csv` (co-occurrence pairs)
3. Graph Build → `graphs/*.edg` (edgelists)
4. Embedding → `embeddings/*.wv` (trained models)

## Git Tracking

**Tracked**: `processed/*.csv` (small, source-controlled pairs), documentation

**Not Tracked** (see `.gitignore`): `embeddings/`, `graphs/`, `raw/`, `cache/`, `archive/`

## Size Guidelines

- Pairs CSV: 1-50 MB
- EDG file: 1-50 MB
- Embeddings: 10-200 MB
- Raw data: 500 MB - 2 GB

Large files (>100MB) should not be committed to git.
