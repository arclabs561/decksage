#!/usr/bin/env bash
# Make the local Compose stack healthy again, or report what still is not.
#
# Idempotent: safe to run at any time. It does not delete volumes or data.
#
#   1. start/recreate services with health gating (--wait)
#   2. if /live is not 200, restart the API once, then rebuild if still down
#   3. verify the served frontend matches the working tree (bind mounts)
#   4. print the service table and exit non-zero only if something is unresolved
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
BASE_URL="${BASE_URL:-http://127.0.0.1:${API_PORT:-8000}}"
BUILD=0
[ "${1:-}" = "--build" ] && BUILD=1

wait_live() {
  for _ in $(seq 1 30); do
    if curl -fsS -m 3 "${BASE_URL}/live" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo "==> compose up (health-gated)"
if [ "$BUILD" = "1" ]; then
  "${COMPOSE[@]}" up -d --build --wait
else
  "${COMPOSE[@]}" up -d --wait
fi

if ! wait_live; then
  echo "==> API is not live; restarting once"
  "${COMPOSE[@]}" restart api >/dev/null
  if ! wait_live; then
    echo "==> still not live; rebuilding the API image"
    "${COMPOSE[@]}" up -d --build --wait api
    wait_live || true
  fi
fi

echo "==> frontend sync"
sync_failed=0
while read -r url file; do
  if [ -f "$file" ]; then
    served=$(curl -fsS -m 5 "${BASE_URL}${url}" | shasum -a 256 | cut -d' ' -f1)
    local_hash=$(shasum -a 256 "$file" | cut -d' ' -f1)
    if [ "$served" != "$local_hash" ]; then
      echo "  STALE ${url} (container != working tree)"
      sync_failed=1
    else
      echo "  ok   ${url}"
    fi
  fi
done <<'EOF'
/search.html frontend/test_search.html
/static/retro.css frontend/static/retro.css
EOF

echo "==> text cache"
if compgen -G "data/cache/*.partial.npz" >/dev/null; then
  echo "  WARN partial cache present: an index extension was interrupted."
  echo "       Resume with: docker cp scripts/training/extend_text_cache.py decksage-api:/app/extend_text_cache.py && docker exec decksage-api python /app/extend_text_cache.py"
else
  echo "  ok   no partial cache"
fi

echo "==> services"
"${COMPOSE[@]}" ps

if ! wait_live || [ "$sync_failed" = "1" ]; then
  echo "==> unresolved: API live or frontend sync still failing" >&2
  exit 1
fi
echo "==> stack healthy"
