# Refresh and the MPS boundary

Docker Desktop on macOS runs a Linux VM. Metal/MPS is not exposed to Linux
containers. Docker's own macOS GPU feature (Model Runner with vllm-metal)
works around this by running the accelerator natively on the host and talking
to it over TCP; that is the supported pattern. The Podman/krunkit Vulkan
workaround reaches ~77% of native Metal through MoltenVK but does not apply to
Docker Desktop. Our equivalent is a small host embedding bridge:

```bash
scripts/ops/install_mps_bridge_agent.sh   # keeps it alive at login
# endpoint: http://127.0.0.1:8765/health, POST /embed
```

`bootstrap` uses it when `MPS_BRIDGE_URL` is set (Compose adds
`host.docker.internal:host-gateway`), so the CPU fallback remains.

The split is:

- **Host**: embedding, cache builds, tag/reprint artifacts, any training.
  `scripts/ops/refresh_all.sh` uses `uv run --with sentence-transformers --with
  torch` and `--device auto`, which selects MPS when available.
- **Compose**: serving, Meilisearch, Qdrant, and the CPU-only `bootstrap`
  profile (`just bootstrap`) as a fallback when the host path is unavailable.

## What refresh does

1. Rebuilds `data/processed/magic_tags.json` and `magic_reprints.json`.
2. Tops up the E5 caches for all games (no-op when complete).
3. Rebuilds the Magic unified graph (`scripts/graph/build_unified_graph.py`).
4. Fills Meilisearch gaps (`bootstrap_index.py`) without deleting documents.
5. Restarts the API so it loads the new artifacts.
6. Runs `dev-doctor` and exits non-zero if the stack is not healthy.

`just refresh` is the manual entry point. For a schedule, install the daily
LaunchAgent:

```bash
scripts/ops/install_refresh_agent.sh
```

It writes `~/Library/LaunchAgents/com.decksage.refresh.plist` (04:00 daily) and
logs to `~/.agents/logs/decksage-refresh.log`.

The container `bootstrap` remains CPU-only by design; its text-cache build is
slower than the host path and exists so a bare compose stack can still fill
itself.

## What is not automatic yet

- Training a new ranker: there is no served model to refresh; rerun
  `scripts/training/train_functional_ranker.py` after new labels.
- Unified graph rebuild: the retrieval graph is text + tag + co-occurrence
  union at query time; a persisted multi-relation edge store is still open.
