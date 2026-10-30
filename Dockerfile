# DeckSage API Dockerfile
# Multi-stage build: heavy deps cached in builder, thin runtime image

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps only (source is copied below, then refreshed by Compose Watch in dev)
# sentence-transformers carries the E5 text embedder and the SigLIP visual path;
# without it /v1/search cannot embed a query and both signals report missing.
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache -e "." && \
    uv pip install --system --no-cache uvicorn[standard] gensim POT sentence-transformers

# Runtime stage
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Runtime source. Compose Watch syncs edits over this copy in development; a
# production build ships it as-is. src/backend (Go tooling) is not part of it.
COPY src/ml ./src/ml
COPY frontend ./frontend

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/live || exit 1

EXPOSE ${PORT}

CMD ["uvicorn", "src.ml.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
