# Starting Services

## Current Status

The API is running but needs Meilisearch to be started.

## Required Services

1. **Meilisearch** (Port 7700) - Not running
2. **Qdrant** (Port 6333) - May not be running
3. **API** (Port 8000) - ✅ Running
4. **React Frontend** (Port 3001) - Not running

## Start Commands

### Option 1: Docker (if available)
```bash
# Start Meilisearch
docker run -d -p 7700:7700 getmeili/meilisearch:latest

# Start Qdrant
docker run -d -p 6333:6333 qdrant/qdrant:latest
```

### Option 2: Manual Installation
```bash
# Install Meilisearch
curl -L https://install.meilisearch.com | sh
./meilisearch --http-addr 127.0.0.1:7700

# Install Qdrant
# See: https://qdrant.tech/documentation/guides/installation/
```

### Option 3: Make API work without Meilisearch
The API currently requires Meilisearch. We could modify it to work with just embeddings/Qdrant.

## Next Steps

1. Start Meilisearch on port 7700
2. Start Qdrant on port 6333 (if using vector search)
3. Restart API
4. Start React frontend
