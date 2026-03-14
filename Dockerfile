# DeckSage API Dockerfile
# Multi-stage build: heavy deps cached in builder, thin runtime image

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps only (source is bind-mounted in dev, copied in prod)
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache -e "." && \
    uv pip install --system --no-cache uvicorn[standard] gensim POT

# Runtime stage
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/live || exit 1

EXPOSE ${PORT}

CMD ["uvicorn", "src.ml.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
