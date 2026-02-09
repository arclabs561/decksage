# Card search (Meilisearch + Qdrant)

DeckSage exposes `/v1/search` as an optional hybrid search endpoint:

- **Meilisearch**: text/keyword search
- **Qdrant**: vector search (requires embeddings)

In multi-game serving, requests must specify `game`.

## Setup

Start backends (Docker):

```bash
docker run -d -p 7700:7700 getmeili/meilisearch:latest
docker run -d -p 6333:6333 qdrant/qdrant
```

## Namespacing (multi-game)

The API defaults to per-game namespaces:

- **Meilisearch index**: `cards_<game>` (override: `MEILISEARCH_INDEX_<GAME>`)
- **Qdrant collection**: `cards_<game>` (override: `QDRANT_COLLECTION_<GAME>`)

If you index into different names, set the env vars (or pass explicit names when indexing).

## Indexing cards

Index from an embeddings file:

```bash
python -m ml.search.index_cards \
  --game magic \
  --embeddings data/embeddings/magic.wv \
  --meilisearch-url http://localhost:7700 \
  --qdrant-url http://localhost:6333
```

Override names:

```bash
python -m ml.search.index_cards \
  --embeddings data/embeddings/magic.wv \
  --index-name cards_magic \
  --collection-name cards_magic
```

## API usage

### POST

```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "game": "magic",
    "query": "lightning bolt",
    "limit": 10,
    "text_weight": 0.5,
    "vector_weight": 0.5
  }'
```

### GET

```bash
curl "http://localhost:8000/v1/search?game=magic&q=lightning+bolt&limit=10&text_weight=0.5&vector_weight=0.5"
```

## Configuration

Backends:

- `MEILISEARCH_URL` (default: `http://localhost:7700`)
- `MEILISEARCH_KEY` (optional)
- `QDRANT_URL` (default: `http://localhost:6333`)
- `QDRANT_API_KEY` (optional)

Per-game namespaces:

- `MEILISEARCH_INDEX_<GAME>`
- `QDRANT_COLLECTION_<GAME>`
