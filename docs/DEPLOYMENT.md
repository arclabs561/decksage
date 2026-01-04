# Deployment Guide

How to deploy DeckSage API to production (Fly.io) - **Private Tailscale Network Only**.

This deployment is configured for private access via Tailscale only. The app is not publicly accessible.

## Pre-Deployment Checklist

Before deploying, ensure:

1. **All tests pass**: `just test` (fast + slow)
2. **Linting passes**: `just lint` (Ruff) + `golangci-lint` (Go)
3. **Type checking**: `uvx ty check src/ml` (non-blocking but recommended)
4. **Data lineage valid**: `python3 scripts/data_processing/validate_lineage.py`
5. **Model validation**: `scripts/validate_deployment.sh [model_path]`
6. **Docker builds**: `docker build -f Dockerfile.api -t decksage-api .`
7. **Health check works**: API responds to `GET /live`

## Private Network Setup (Tailscale)

This app is configured for **private access only** via Tailscale. It is not publicly accessible.

### Option 1: Tailscale Router (Recommended)

1. **Create Tailscale router app** (one-time setup):
   ```bash
   fly apps create -o tailscale-router
   cd /path/to/tailscale-router
   # Use fly-apps/tailscale-router image or custom Dockerfile
   ```

2. **Get your Fly.io 6PN (private IPv6 network)**:
   ```bash
   fly ips private
   # Example output: fdaa:3:d3ad:beef:192:2ef7:abcf:2
   # Use /48 subnet: fdaa:3:d3ad::/48
   ```

3. **Configure Tailscale router** with your 6PN subnet in `fly.toml`:
   ```toml
   [env]
     TS_ROUTES = "fdaa:3:d3ad::/48"  # Your 6PN subnet
   ```

4. **Set Tailscale auth key**:
   ```bash
   fly secrets set --app tailscale-router TS_AUTHKEY="tskey-client-<your-key>"
   ```

5. **Deploy router**:
   ```bash
   fly deploy --app tailscale-router
   ```

6. **Access DeckSage via Tailscale**:
   - The app will be accessible at its private IPv6 address
   - Or via Tailscale hostname if configured

### Option 2: Direct Tailscale Connection

To connect the app directly to Tailscale (requires modifying Dockerfile):

1. **Generate Tailscale auth key** (pre-approved, one-time):
   ```bash
   # In Tailscale admin console, create reusable auth key
   ```

2. **Set secret**:
   ```bash
   fly secrets set TAILSCALE_AUTHKEY="tskey-<your-key>"
   ```

3. **Modify Dockerfile** to install and run tailscaled (see Tailscale docs)

## Manual Deployment

```bash
# 1. Build Docker image
docker build -f Dockerfile.api -t decksage-api .

# 2. Validate deployment
./scripts/validate_deployment.sh data/embeddings/production.wv

# 3. Deploy to Fly.io (private network only)
flyctl deploy --dockerfile Dockerfile.api

# 4. Get private IP address
flyctl ips private --app decksage
# Access via: http://[private-ip]:8000 (from Tailscale network)
```

## Automated Deployment (GitHub Actions)

**Trigger**: Push to `main` branch with `[deploy]` in commit message
**Workflow**: `.github/workflows/deploy.yml`
**Steps**:
1. Run all CI checks (lint, test, type-check)
2. Build Docker image
3. Validate deployment
4. Deploy to Fly.io (if all checks pass)

**Setup**: Add `FLY_API_TOKEN` to GitHub secrets for automated deployment.

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

Fly.io automatically checks `/live` every 30s via private network.

## Accessing the Private API

Since this app is private-only:

1. **Via Tailscale router**: Access via Tailscale hostname or private IP
2. **Via private IPv6**: Use `flyctl ips private` to get the address
3. **Via Fly.io WireGuard**: Connect via `flyctl proxy 8000:8000`

**Note**: The app has no public HTTP service. All access is via private network.

## Rollback

If deployment fails:
```bash
flyctl releases list
flyctl releases rollback [release-id]
```

## Common Issues

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
