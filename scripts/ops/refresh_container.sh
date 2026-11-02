#!/usr/bin/env bash
# Refresh the data plane from inside the stack. Compose owns the schedule:
# `docker compose --profile refresh run --rm refresh` or the long-running
# `scheduler` profile. No host launch agents are involved.
#
# Idempotent: every step skips when its inputs are unchanged, so a quiet run
# costs seconds and writes nothing.
set -euo pipefail

API="${API_URL:-http://api:8000}"
GAMES="${DECKSAGE_GAMES:-magic,pokemon,yugioh}"

echo "==> scryfall set/legality/price metadata"
python scripts/data/build_scryfall_metadata.py

echo "==> tag/reprint artifacts"
python scripts/data/build_signal_artifacts.py --all

echo "==> unified graphs"
IFS=',' read -r -a game_list <<<"$GAMES"
for game in "${game_list[@]}"; do
	python scripts/graph/build_unified_graph.py --game "$game" --if-stale
done

echo "==> E5 text vectors (catalog cards without graph vectors)"
for game in "${game_list[@]}"; do
  python scripts/embed/build_text_vector_index.py --game "$game"
done

echo "==> meilisearch fill + payload backfill"
python scripts/data/bootstrap_index.py --all --payloads --text

echo "==> reload artifacts (no restart)"
if curl -fsS -m 120 -X POST "$API/v1/admin/reload" >/dev/null; then
	echo "api reloaded"
else
	echo "reload failed; the API will pick the artifacts up on its next start" >&2
fi
