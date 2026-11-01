#!/usr/bin/env python3
"""Rebuild Meilisearch card documents from the enriched catalogs.

The API's first-boot index only ran on an empty index and stored a narrow
document. This rebuild is explicit, idempotent per run, and writes every card
attribute the catalogs carry (power, toughness, archetype, hp, atk/def,
effect types, ...), then applies the current filterable/sortable settings.

Usage:
    scripts/data/reindex_meilisearch_index.py --all --reindex
    scripts/data/reindex_meilisearch_index.py --game magic --reindex
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml.search.hybrid_search import build_meilisearch_settings
from ml.search.meili_docs import card_document


def _set_lookup() -> dict[str, dict]:
    """Scryfall set/set_name by card; the catalog CSV has neither column."""
    path = ROOT / "data" / "processed" / "scryfall_sets.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def documents(game: str) -> list[dict]:
    path = ROOT / "data" / "processed" / f"card_attributes_{game}_enriched.csv"
    frame = pd.read_csv(path, low_memory=False)
    set_lookup = _set_lookup() if game == "magic" else {}
    docs: list[dict] = []
    for _, row in frame.iterrows():
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        meta = {
            key: value
            for key, value in row.to_dict().items()
            if not (isinstance(value, float) and value != value)
        }
        set_info = set_lookup.get(name)
        if set_info:
            for key in ("set", "set_name", "released_at"):
                if set_info.get(key):
                    meta[key] = set_info[key]
        doc_id = hashlib.sha1(name.encode()).hexdigest()[:16]
        docs.append(card_document(name, meta, game, doc_id))
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", action="append", choices=("magic", "pokemon", "yugioh"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--reindex", action="store_true", help="delete and recreate the index")
    parser.add_argument("--url", default=os.getenv("MEILISEARCH_URL", "http://127.0.0.1:7700"))
    parser.add_argument("--key", default=os.getenv("MEILISEARCH_KEY", ""))
    args = parser.parse_args()
    games = ["magic", "pokemon", "yugioh"] if args.all else (args.game or [])

    from meilisearch import Client

    client = Client(args.url, args.key)
    for game in games:
        docs = documents(game)
        index = client.index(f"cards_{game}")
        if args.reindex:
            try:
                index.delete()
            except Exception:
                pass
            task = client.create_index(f"cards_{game}", {"primaryKey": "id"})
            client.wait_for_task(task.task_uid, timeout_in_ms=60_000)
            index = client.index(f"cards_{game}")
        task = index.update_settings(build_meilisearch_settings(game))
        if getattr(task, "task_uid", None) is not None:
            client.wait_for_task(task.task_uid, timeout_in_ms=60_000)
        for start in range(0, len(docs), 500):
            batch = docs[start : start + 500]
            task = index.add_documents(batch)
            if getattr(task, "task_uid", None) is not None:
                client.wait_for_task(task.task_uid, timeout_in_ms=120_000)
        print(f"{game}: {len(docs)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
