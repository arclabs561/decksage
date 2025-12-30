# syntax=docker/dockerfile:1
# Dockerfile for DeckSage API on Fly.io
# Aggressively optimized with extensive cache mounts for maximum build speed

# Builder stage - installs dependencies
FROM python:3.11-slim AS builder

# Install uv (cache this layer - rarely changes)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy only dependency files first (enables better caching)
# This layer only invalidates when dependencies change
COPY pyproject.toml ./

# Install dependencies with extensive cache mounts
# Multiple cache mounts for different package manager caches
# Cache persists across builds, only downloads new/changed packages
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-cache \
    --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    --mount=type=cache,target=/root/.cache/pip/wheels,id=pip-wheels \
    --mount=type=cache,target=/root/.cache/pip/http,id=pip-http \
    --mount=type=cache,target=/root/.local/share/uv,id=uv-data \
    uv pip install --system -e .[api]

# Runtime stage - minimal final image
FROM python:3.11-slim

# Install uv in runtime (lightweight, just the binary)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy installed packages from builder (only what's needed)
# Use cache mount to speed up this copy operation
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code last (changes most frequently)
# This layer invalidates on code changes, but dependencies stay cached
# Use bind mount for faster copying in some scenarios, but COPY is better for final image
COPY src/ml ./src/ml
COPY pyproject.toml ./

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/live')"

# Run the API
CMD ["uvicorn", "src.ml.api.api:app", "--host", "0.0.0.0", "--port", "8000"]

