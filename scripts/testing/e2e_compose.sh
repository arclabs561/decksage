#!/usr/bin/env bash
# Run the Playwright suite against the composed stack, not a bare uvicorn.
#
# The stack is rebuilt from the working tree first. That is deliberate: the
# frontend reaches the container through Compose Watch, and when the watch
# process is not running the container keeps serving an older copy. Tests that
# ran against the stale copy reported bugs that were already fixed (and hid
# ones that were not).
#
# Usage:
#   scripts/testing/e2e_compose.sh                 # rebuild, then all core specs
#   scripts/testing/e2e_compose.sh tests/e2e/regressions.spec.mjs
#
# Requires Docker with Compose v2 and the repo's node_modules.
set -euo pipefail

cd "$(dirname "$0")/../.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
BASE_URL="${BASE_URL:-http://127.0.0.1:${API_PORT:-8000}}"

echo "==> building and starting the dev stack"
"${COMPOSE[@]}" up -d --build --wait

echo "==> waiting for ${BASE_URL}/live"
for _ in $(seq 1 30); do
	if curl -fsS -m 3 "${BASE_URL}/live" >/dev/null 2>&1; then
		break
	fi
	sleep 2
done
curl -fsS -m 5 "${BASE_URL}/live" >/dev/null || {
	echo "API did not become live at ${BASE_URL}" >&2
	"${COMPOSE[@]}" logs --tail 40 api >&2
	exit 1
}

if [ "$#" -eq 0 ]; then
	set -- \
		tests/e2e/api-health.spec.mjs \
		tests/e2e/search.spec.mjs \
		tests/e2e/card-details.spec.mjs \
		tests/e2e/regressions.spec.mjs
fi

echo "==> running: $*"
BASE_URL="${BASE_URL}" COMPOSE_E2E=1 npx playwright test "$@"
