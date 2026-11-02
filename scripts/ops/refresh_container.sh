#!/bin/sh
# Refresh the data plane from inside the stack. Compose owns the schedule:
# `docker compose --profile refresh run --rm refresh` or the long-running
# `scheduler` profile. No host launch agents are involved.
#
# Every step is independent: a failure is recorded and the run continues, so one
# broken backend does not block the artifacts the others need. The script exits
# non-zero at the end if anything failed.
#
# Idempotent: each builder skips when its inputs are unchanged, so a quiet run
# costs seconds and writes nothing.
set -u

API="${API_URL:-http://api:8000}"
GAMES="${DECKSAGE_GAMES:-magic,pokemon,yugioh}"
failures=0
steps=0

step() {
	label=$1
	shift
	steps=$((steps + 1))
	echo "==> ${label}"
	if ! "$@"; then
		echo "FAILED: ${label}" >&2
		failures=$((failures + 1))
	fi
}

games=$(printf '%s' "$GAMES" | tr ',' ' ')

step "scryfall set/legality/price metadata" \
	python scripts/data/build_scryfall_metadata.py

step "tag/reprint artifacts" \
	python scripts/data/build_signal_artifacts.py --all

for game in $games; do
	step "unified graph (${game})" \
		python scripts/graph/build_unified_graph.py --game "$game" --if-stale
done

for game in $games; do
	step "E5 text vectors (${game})" \
		python scripts/embed/build_text_vector_index.py --game "$game"
done

step "meilisearch fill, payload backfill, text caches" \
	python scripts/data/bootstrap_index.py --all --payloads --text

step "topology check" \
	python scripts/ops/topology.py check

step "reload artifacts (no restart)" \
	curl -fsS -m 120 -X POST "$API/v1/admin/reload" -o /dev/null

if [ "$failures" -ne 0 ]; then
	echo "refresh finished with ${failures}/${steps} failed step(s)" >&2
	exit 1
fi
echo "refresh finished: ${steps}/${steps} steps ok"
