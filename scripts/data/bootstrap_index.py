#!/usr/bin/env python3
"""Self-fill the search indexes from the catalogs.

Idempotent: compares counts, adds only when a backend is short, and can build
a missing E5 text cache. Designed to run as a one-shot Compose service or from
`just bootstrap`; it never deletes data.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

from rebuild_meilisearch_index import documents

from ml.search.hybrid_search import build_meilisearch_settings


def cache_names(game: str, cache_dir: Path) -> int:
    path = cache_dir / f"text_emb_cache_cards_{game}_intfloat-e5-base-v2.names.json"
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text()))
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", action="append", choices=("magic", "pokemon", "yugioh"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--text", action="store_true", help="build missing E5 caches")
    parser.add_argument("--url", default=os.getenv("MEILISEARCH_URL", "http://127.0.0.1:7700"))
    parser.add_argument("--key", default=os.getenv("MEILISEARCH_KEY", ""))
    args = parser.parse_args()
    games = ["magic", "pokemon", "yugioh"] if args.all else (args.game or [])

    from meilisearch import Client

    client = Client(args.url, args.key)
    cache_dir = ROOT / "data" / "cache"
    for game in games:
        docs = documents(game)
        catalog = len(docs)
        index = client.index(f"cards_{game}")
        try:
            current = index.get_stats().number_of_documents
        except Exception:
            client.create_index(f"cards_{game}", {"primaryKey": "id"})
            index = client.index(f"cards_{game}")
            current = 0
        if current >= catalog:
            print(f"{game}: meili {current}/{catalog}, no fill needed")
        else:
            task = index.update_settings(build_meilisearch_settings(game))
            if getattr(task, "task_uid", None) is not None:
                client.wait_for_task(task.task_uid, timeout_in_ms=60_000)
            for start in range(0, len(docs), 500):
                task = index.add_documents(docs[start : start + 500])
                if getattr(task, "task_uid", None) is not None:
                    client.wait_for_task(task.task_uid, timeout_in_ms=120_000)
            print(f"{game}: meili filled {current} -> {catalog}")

        if args.text:
            cached = cache_names(game, cache_dir)
            if cached >= catalog:
                print(f"{game}: text cache {cached}/{catalog}")
            else:
                script = ROOT / "scripts" / "training" / "extend_text_cache.py"
                print(f"{game}: text cache {cached}/{catalog}; building")
                completed = subprocess.run(
                    [sys.executable, str(script), "--game", game], check=False
                )
                if completed.returncode != 0:
                    print(f"{game}: text build failed ({completed.returncode})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
