# DeckSage API Dockerfile
# Multi-stage build for optimized image size

FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies
RUN uv pip install --system --no-cache -e ".[api,embeddings]" && \
    uv pip install --system --no-cache uvicorn[standard]

# Runtime stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
WORKDIR /app
COPY src/ ./src/
COPY test_search.html ./

# Serve static files (test_search.html)
# The API will serve this via FastAPI static files

# Create directories for ML assets (will be mounted as volumes)
RUN mkdir -p /app/data/embeddings \
    /app/data/graphs \
    /app/data/attributes \
    /app/data/signals

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/live || exit 1

# Expose port
EXPOSE ${PORT}

# Copy indexing script
COPY scripts/docker/index_cards_on_startup.py /app/scripts/docker/

# Run the API (with optional indexing on startup)
# Set INDEX_ON_STARTUP=true to auto-index cards
CMD ["sh", "-c", "if [ \"$INDEX_ON_STARTUP\" = \"true\" ] && [ -f \"$EMBEDDINGS_PATH\" ]; then python /app/scripts/docker/index_cards_on_startup.py --embeddings \"$EMBEDDINGS_PATH\" --meilisearch-url \"${MEILISEARCH_URL:-http://meilisearch:7700}\" --qdrant-url \"${QDRANT_URL:-http://qdrant:6333}\" --skip-if-exists || echo 'Indexing failed, continuing anyway...'; fi && uvicorn src.ml.api.api:app --host 0.0.0.0 --port 8000"]

