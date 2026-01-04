# AI Agent Deployment Guide

**For AI Agents (Cursor, Claude, etc.)**: This guide explains how to deploy DeckSage to production and what checks must pass before deployment.

## Deployment Architecture

**Platform**: Fly.io
**Container**: Docker (multi-stage build)
**API**: FastAPI (uvicorn)
**Health Check**: `/live` endpoint

## Pre-Deployment Checklist

Before deploying, ensure:

1. **All tests pass**: `just test` (fast + slow)
2. **Linting passes**: `just lint` (Ruff) + `golangci-lint` (Go)
3. **Type checking**: `uvx ty check src/ml` (non-blocking but recommended)
4. **Data lineage valid**: `python3 scripts/data_processing/validate_lineage.py`
5. **Model validation**: `scripts/validate_deployment.sh [model_path]`
6. **Docker builds**: `docker build -f Dockerfile.api -t decksage-api .`
7. **Health check works**: API responds to `GET /live`

## Deployment Workflow

### Manual Deployment (Current)

```bash
# 1. Build Docker image
docker build -f Dockerfile.api -t decksage-api .

# 2. Validate deployment
./scripts/validate_deployment.sh data/embeddings/production.wv

# 3. Deploy to Fly.io
flyctl deploy --dockerfile Dockerfile.api
```

### Automated Deployment (GitHub Actions)

**Trigger**: Push to `main` branch with `[deploy]` in commit message
**Workflow**: `.github/workflows/deploy.yml`
**Steps**:
1. Run all CI checks (lint, test, type-check)
2. Build Docker image
3. Validate deployment
4. Deploy to Fly.io (if all checks pass)

## Deployment Validation

The `scripts/validate_deployment.sh` script checks:
- Production model file exists
- Model is valid (loadable, has vocabulary)
- Model can perform similarity queries
- Model dimensions match expected

## Environment Variables

Required for deployment:
- `PORT=8000` (set in Dockerfile)
- `PYTHONUNBUFFERED=1` (set in Dockerfile)
- `EMBEDDINGS_PATH` (optional, defaults to production model)

## Health Checks

**Liveness**: `GET /live` - Returns 200 if API is running
**Readiness**: `GET /ready` - Returns 200 if API is ready to serve requests

Fly.io automatically checks `/live` every 30s.

## Rollback

If deployment fails:
```bash
flyctl releases list
flyctl releases rollback [release-id]
```

## For AI Agents

When modifying deployment-related code:
1. **Always test Docker build**: `docker build -f Dockerfile.api -t test-api .`
2. **Check health endpoints**: Ensure `/live` and `/ready` work
3. **Validate model paths**: Use `PATHS` utility, not hardcoded paths
4. **Update fly.toml**: If changing ports, memory, or regions
5. **Test locally first**: `./scripts/start_api.sh` before deploying

## Common Deployment Issues

| Issue | Solution |
|-------|----------|
| Docker build fails | Check `pyproject.toml` dependencies |
| Health check fails | Verify `/live` endpoint exists |
| Model not found | Check `EMBEDDINGS_PATH` or default path |
| Port conflict | Verify `PORT=8000` in Dockerfile |
| Memory issues | Increase `memory_mb` in `fly.toml` |

## Related Files

- `Dockerfile.api` - Docker build configuration
- `fly.toml` - Fly.io deployment configuration
- `scripts/validate_deployment.sh` - Pre-deploy validation
- `scripts/start_api.sh` - Local API startup (for testing)
- `.github/workflows/deploy.yml` - Automated deployment
