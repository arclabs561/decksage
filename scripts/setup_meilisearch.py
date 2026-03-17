#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["meilisearch>=0.31"]
# ///
"""Configure MeiliSearch indices for DeckSage.

Applies ranking rules, searchable/filterable/sortable attributes, synonyms,
and typo tolerance to per-game card indices. Idempotent -- safe to run
repeatedly; skips if settings already match.

Usage:
    uv run scripts/setup_meilisearch.py
    uv run scripts/setup_meilisearch.py --url http://meilisearch:7700
    uv run scripts/setup_meilisearch.py --games magic,yugioh
    uv run scripts/setup_meilisearch.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Add src/ to path so we can import the shared settings builder.
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from ml.search.hybrid_search import build_meilisearch_settings  # noqa: E402

try:
    from meilisearch import Client as MeilisearchClient
    from meilisearch.errors import MeilisearchApiError
except ImportError:
    print("meilisearch package not installed. Install with: uv add meilisearch")
    sys.exit(1)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("setup_meilisearch")


def _settings_match(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Return True if all keys in *desired* match values in *current*."""
    for key, val in desired.items():
        if current.get(key) != val:
            return False
    return True


def configure_index(
    client: MeilisearchClient,
    index_name: str,
    game: str,
    *,
    dry_run: bool = False,
) -> bool:
    """Configure a single MeiliSearch index.

    Returns True if settings were applied or already matched.
    """
    settings = build_meilisearch_settings(game)

    # Ensure index exists.
    try:
        idx = client.index(index_name)
        idx.fetch_info()
    except MeilisearchApiError as e:
        if "index_not_found" in str(e).lower():
            if dry_run:
                logger.info("[dry-run] Would create index '%s'", index_name)
            else:
                client.create_index(uid=index_name, options={"primaryKey": "id"})
                logger.info("Created index '%s'", index_name)
            idx = client.index(index_name)
        else:
            logger.error("Failed to access index '%s': %s", index_name, e)
            return False

    if dry_run:
        logger.info("[dry-run] Settings for '%s':", index_name)
        logger.info(json.dumps(settings, indent=2, ensure_ascii=False))
        return True

    # Check current settings.
    current = idx.get_settings()
    if _settings_match(current, settings):
        logger.info("Index '%s' already configured (game=%s), skipping", index_name, game)
        return True

    task = idx.update_settings(settings)
    logger.info(
        "Applied settings to '%s' (game=%s) -- task uid=%s",
        index_name,
        game,
        getattr(task, "task_uid", "?"),
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure MeiliSearch indices for DeckSage",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("MEILISEARCH_URL", "http://localhost:7700"),
        help="MeiliSearch URL (default: $MEILISEARCH_URL or http://localhost:7700)",
    )
    parser.add_argument(
        "--key",
        default=os.getenv("MEILISEARCH_KEY"),
        help="MeiliSearch API key (default: $MEILISEARCH_KEY)",
    )
    parser.add_argument(
        "--games",
        default=os.getenv("DECKSAGE_GAMES", "magic,pokemon,yugioh"),
        help="Comma-separated game list (default: magic,pokemon,yugioh)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print settings without applying",
    )
    args = parser.parse_args()

    games = [g.strip().lower() for g in args.games.split(",") if g.strip()]
    if not games:
        logger.error("No games specified")
        return 1

    resolved_key = args.key or None
    client = MeilisearchClient(url=args.url, api_key=resolved_key)

    # Verify connectivity.
    try:
        health = client.health()
        logger.info("MeiliSearch at %s is %s", args.url, health.get("status", "?"))
    except Exception as e:
        logger.error("Cannot connect to MeiliSearch at %s: %s", args.url, e)
        return 1

    ok = True
    for game in games:
        index_name = f"cards_{game}"
        if not configure_index(client, index_name, game, dry_run=args.dry_run):
            ok = False

    if ok:
        logger.info("All indices configured successfully")
    else:
        logger.error("Some indices failed to configure")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
