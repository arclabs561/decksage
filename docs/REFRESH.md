# Refresh: Compose owns it

No host launch agents. The data plane is refreshed by the Compose services
`refresh` (one-shot) and `scheduler` (recurring), both built from the same
image as the API.

```bash
# one run, then exit
docker compose --profile refresh run --rm refresh

# recurring (default every 24h; REFRESH_INTERVAL=<seconds> to change)
docker compose --profile schedule up -d scheduler
docker compose logs -f scheduler
```

## What a refresh does

`scripts/ops/refresh_container.sh`, in order:

1. Rebuilds Scryfall set/legality/price lookups when the bulk file is newer
   (`scripts/data/build_scryfall_metadata.py`).
2. Rebuilds tag/reprint artifacts for every game
   (`scripts/data/build_signal_artifacts.py --all`). Magic tags come from the
   curated tag index; Pokemon and Yu-Gi-Oh! tags are derived from structured
   columns (subtypes, keywords, race, attribute, archetype).
3. Rebuilds the unified graph for each game, skipping when the graph is newer
   than its inputs (`build_unified_graph.py --if-stale`).
4. Mirrors the E5 caches into `cards_<game>_e5` so catalog cards without a
   graph vector still have neighbours (`build_text_vector_index.py`, idempotent).
5. Fills Meilisearch gaps and tops up text caches
   (`bootstrap_index.py --all --payloads --text`).
6. Runs `scripts/ops/topology.py check`, so a refresh that did not converge
   fails instead of reporting success.
7. Calls `POST /v1/admin/reload`, which re-reads metadata, tags, reprints, set
   data and the unified graph in place. No restart, so serving is not
   interrupted and the ~4.7 GB startup is paid once.

Each step runs independently: a failure is counted and the run continues, then
exits non-zero at the end. One broken backend no longer blocks the others.

Every step is idempotent: a run with unchanged inputs writes nothing and takes
seconds. `--if-stale` compares the graph against the text cache, attributes,
tags, the co-occurrence source and the builder script itself.

## Tradeoff: no host GPU

Docker Desktop cannot expose Metal to a Linux container, so graph and cache
builds run on container CPU. The graph's text relation reads the cached E5
matrix (numpy only) and does not re-embed. The tag and attribute relations are a
chunked matmul, not per-pair Python, so a cold Yu-Gi-Oh! rebuild is ~51 s and a
no-op run is seconds (11/11 steps in ~38 s measured).

If a host MPS run is genuinely needed, start the bridge by hand — it is not a
service and there is no agent:

```bash
uv run --with fastapi --with uvicorn --with sentence-transformers --with torch \
  python scripts/ops/mps_bridge.py --port 8765
```

then pass `MPS_BRIDGE_URL=http://host.docker.internal:8765` to `bootstrap` for
that run. The default stack does not need it.

## API reload endpoint

`POST /v1/admin/reload[?game=magic]` reloads derived artifacts from disk. If
`DECKSAGE_ADMIN_TOKEN` is set, the caller must send `X-Admin-Token`.

## API hot reload

The dev overlay no longer hot-reloads the API by default. The reloader spawns a
second worker while the old one drains, and the API holds ~4.7 GB, so an edit
could put two workers over the VM's memory; the observed failure was a reloader
left alive with no worker, where `/live` hung and nothing restarted it. Set
`API_RELOAD=1` while editing Python, or restart the service:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart api
```
