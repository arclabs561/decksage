#!/usr/bin/env bash
# Refresh the data plane and reload the API. Safe to run on a schedule.
#
# Host-side on purpose: Docker Desktop on macOS cannot expose Metal/MPS to a
# Linux container, so embedding/retraining belongs on the host and the
# container only serves the artifacts.
#
#   1. rebuild compact tag/reprint lookups
#   2. top up E5 caches (MPS when available)
#   3. fill Meilisearch gaps
#   4. restart the API so it loads new artifacts
#   5. run the doctor
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
RESTART=1
[ "${1:-}" = "--no-restart" ] && RESTART=0

echo "==> signal artifacts"
uv run python scripts/data/build_signal_artifacts.py

echo "==> text caches (host device auto)"
for game in magic pokemon yugioh; do
  # Host-only MPS: Docker Desktop cannot expose Metal to a Linux container.
  # --with keeps the host ML deps out of the serving venv.
  uv run --with sentence-transformers --with torch \
    python scripts/training/extend_text_cache.py \
    --game "$game" --data-dir data --cache-dir data/cache --device auto
done

echo "==> signal artifacts (tags, reprints)"
uv run python scripts/data/build_signal_artifacts.py --all

for game in magic pokemon yugioh; do
  echo "==> unified graph (${game})"
  uv run python scripts/graph/build_unified_graph.py --game "${game}"
done

echo "==> meilisearch gaps"
MEILISEARCH_URL="http://127.0.0.1:${MEILISEARCH_PORT:-7700}" \
MEILISEARCH_KEY="${MEILISEARCH_KEY:-decksage-dev-meili-key}" \
uv run python scripts/data/bootstrap_index.py --all

# Payloads carry the fields the semantic arm filters on; the backfill is
# idempotent and skips points already at the current schema version.
echo "==> qdrant payload backfill"
uv run python scripts/embed/payload_backfill.py --game all || \
  echo "qdrant payload backfill skipped (qdrant unavailable?)"

if [ "$RESTART" = "1" ]; then
  echo "==> restarting api to load artifacts"
  "${COMPOSE[@]}" restart api >/dev/null
fi

echo "==> doctor"
scripts/dev/stack_doctor.sh
