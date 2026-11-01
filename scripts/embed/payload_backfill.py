#!/usr/bin/env python3
"""Enrich Qdrant payloads so vector search can filter, not just rank.

The original payload was `name, type_line, image_url, text`: enough to render a
result, useless for filtering. This rewrites each point's payload with the
typed fields the retriever filters on (colour, cost, rarity, set, stats) and
creates the payload indexes those filters need.

Idempotent: points keep their ids and vectors; a point whose payload already
carries the current schema version is skipped. Resumable with --checkpoint.

Usage:
    uv run python scripts/embed/backfill_payloads.py --game magic
    uv run python scripts/embed/payload_backfill.py --game all --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml.search.hybrid_search import (
    _QDRANT_KEYWORD_FIELDS,
    _QDRANT_NUMERIC_FIELDS,
    point_id_for,
)
from ml.utils.paths import PATHS


SCHEMA_VERSION = 4  # 4 adds set/set_name from the Scryfall lookup
PROCESSED = PATHS.processed


def numeric(value: str) -> int | float | None:
    text = (value or "").strip().lstrip("+")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def split_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def payload_for(game: str, row: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": row.get("name", ""),
        "text": (row.get("oracle_text") or row.get("text") or "")[:2000],
        "type_line": row.get("type") or row.get("type_line") or "",
        "image_url": row.get("image_url") or "",
        "rarity": (row.get("rarity") or "").lower(),
        "colors": split_list(row.get("colors") or ""),
        "cmc": numeric(row.get("cmc") or ""),
        "set": row.get("set") or "",
        "set_name": row.get("set_name") or "",
        "schema": SCHEMA_VERSION,
    }
    if game == "magic":
        payload["power"] = numeric(row.get("power") or "")
        payload["toughness"] = numeric(row.get("toughness") or "")
    elif game == "pokemon":
        payload["hp"] = numeric(row.get("hp") or "")
        payload["supertype"] = row.get("supertype") or ""
        payload["subtypes"] = split_list(row.get("subtypes") or "")
    elif game == "yugioh":
        payload["atk"] = numeric(row.get("atk") or "")
        payload["def_stat"] = numeric(row.get("def_stat") or "")
        payload["level"] = numeric(row.get("level_rank_link") or "")
        payload["archetype"] = row.get("archetype_enriched") or row.get("archetype") or ""
        payload["attribute"] = row.get("attribute") or ""
        payload["race"] = row.get("race_enriched") or row.get("race") or ""
    return {key: value for key, value in payload.items() if value not in ("", None, [])}


def load_rows(game: str) -> dict[str, dict[str, str]]:
    path = PROCESSED / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        raise SystemExit(f"missing card metadata: {path}")
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        rows = {row.get("name", ""): row for row in csv.DictReader(handle) if row.get("name")}
    # The CSV has no set or set_name; merge them so payload filters work.
    sets_path = PROCESSED / "scryfall_sets.json"
    if game == "magic" and sets_path.exists():
        set_data = json.loads(sets_path.read_text(encoding="utf-8"))
        for name, row in rows.items():
            info = set_data.get(name)
            if not info:
                continue
            if info.get("set_name"):
                row["set_name"] = info["set_name"]
            if info.get("set"):
                row["set"] = info["set"]
    return rows


def connect(url: str):
    from qdrant_client import QdrantClient

    return QdrantClient(url=url)


def backup_index(client, collection: str) -> None:
    try:
        info = client.get_collection(collection)
        logger_free = {
            "points": getattr(info, "points_count", None),
            "config": "vectors untouched; payload rewritten in place",
        }
        print(json.dumps(logger_free))
    except Exception as exc:
        print(f"collection {collection} not readable: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic", choices=("magic", "pokemon", "yugioh", "all"))
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--checkpoint", type=Path, default=PATHS.processed / ".payload_backfill.json"
    )
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.game == "all" else [args.game]

    checkpoint: dict[str, Any] = {}
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text())
    if args.dry_run:
        for game in games:
            rows = load_rows(game)
            sample = next(iter(rows.values()))
            print(f"{game}: {len(rows)} rows; sample payload {payload_for(game, sample)}")
        return 0

    from qdrant_client import models

    client = connect(args.url)
    for game in games:
        collection = f"cards_{game}"
        rows = load_rows(game)
        print(f"== {game}: {len(rows)} metadata rows, collection {collection}")
        backup_index(client, collection)

        for field in sorted(_QDRANT_KEYWORD_FIELDS):
            try:
                client.create_payload_index(
                    collection_name=collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:
                print(f"  index {field}: {exc}")
        for field in sorted(_QDRANT_NUMERIC_FIELDS):
            try:
                client.create_payload_index(
                    collection_name=collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.FLOAT,
                )
            except Exception as exc:
                print(f"  index {field}: {exc}")

        seen = checkpoint.get(collection, {}).get("done", [])
        offset = checkpoint.get(collection, {}).get("offset")
        updated = skipped = 0
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                limit=args.batch,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if not points:
                break
            batch = []
            for point in points:
                name = (point.payload or {}).get("name", "")
                if (point.payload or {}).get("schema") == SCHEMA_VERSION:
                    skipped += 1
                    continue
                row = rows.get(name)
                if row is None:
                    skipped += 1
                    continue
                batch.append(
                    models.PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=payload_for(game, row),
                    )
                )
            if batch:
                client.upsert(collection_name=collection, points=batch)
                updated += len(batch)
            checkpoint[collection] = {"offset": offset, "done": seen}
            args.checkpoint.write_text(json.dumps(checkpoint, indent=1))
            print(f"  updated={updated} skipped={skipped}", flush=True)
            if offset is None:
                break

        checkpoint[collection] = {"offset": None, "done": sorted(set(seen))}
        args.checkpoint.write_text(json.dumps(checkpoint, indent=1))
        sample_points, _ = client.scroll(collection_name=collection, limit=1, with_payload=True)
        if sample_points:
            payload = sample_points[0].payload or {}
            print(
                f"  wrote {updated}, skipped {skipped}; sample {payload.get('name')}: "
                f"{sorted(payload)}"
            )
        print("  ids are stable (point_id_for), so reruns overwrite rather than duplicate")
        print(f"  example id {point_id_for('Lightning Bolt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
