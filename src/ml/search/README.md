# Card Search with Meilisearch + Qdrant

Hybrid card search combining:
- **Meilisearch**: Fast text/keyword search on card names and text
- **Qdrant**: Semantic vector search using card embeddings

## Setup

1. Install dependencies:
```bash
uv add qdrant-client meilisearch
```

2. Start Meilisearch (Docker):
```bash
docker run -d -p 7700:7700 getmeili/meilisearch:latest
```

3. Start Qdrant (Docker):
```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

## Indexing Cards

Index cards from your embeddings file:

```bash
python -m ml.search.index_cards \
  --embeddings data/embeddings/magic_128d_test_pecanpy.wv \
  --meilisearch-url http://localhost:7700 \
  --qdrant-url http://localhost:6333
```

## API Usage

The search endpoint is available at `/v1/search`:

### POST Request
```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "lightning bolt",
    "limit": 10,
    "text_weight": 0.5,
    "vector_weight": 0.5
  }'
```

### GET Request
```bash
curl "http://localhost:8000/v1/search?q=lightning+bolt&limit=10&text_weight=0.5&vector_weight=0.5"
```

### Response
```json
{
  "query": "lightning bolt",
  "total": 10,
  "results": [
    {
      "card_name": "Lightning Bolt",
      "score": 0.95,
      "source": "hybrid",
      "metadata": {
        "image_url": "...",
        "ref_url": "..."
      }
    }
  ]
}
```

## Python Usage

```python
from ml.search import HybridSearch
from gensim.models import KeyedVectors

# Load embeddings
embeddings = KeyedVectors.load("data/embeddings/model.wv")

# Create search client
search = HybridSearch(embeddings=embeddings)

# Search
results = search.search("lightning bolt", limit=10)

for result in results:
    print(f"{result.card_name}: {result.score} ({result.source})")
```

## Configuration

Environment variables:
- `MEILISEARCH_URL`: Meilisearch server URL (default: http://localhost:7700)
- `MEILISEARCH_KEY`: Meilisearch API key (optional)
- `QDRANT_URL`: Qdrant server URL (default: http://localhost:6333)
- `QDRANT_API_KEY`: Qdrant API key (optional)
