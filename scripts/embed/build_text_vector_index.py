#!/usr/bin/env python3
"""Index the E5 text cache into Qdrant so catalog-only cards have neighbours.

The graph collection `cards_{game}` holds 128-D co-occurrence vectors and only
covers the graph vocabulary (25,892 of 36,453 Magic cards). A card that exists
in the catalog but has no co-occurrence edges therefore had no vector at all:
`/v1/similar` returned an empty list and `/v1/search` skipped its vector arm.

Every catalog card does have a 768-D E5 document vector in
`data/cache/text_emb_cache_cards_{game}_intfloat-e5-base-v2.npz` (37,214
names). This script mirrors that cache into a second collection
`cards_{game}_e5`, with the same typed payload the graph collection carries so
semantic hits can be filtered by colour, cost, rarity and set.

The graph collection is never read for writing, recreated, or deleted: the new
collection is additive and can be dropped without losing anything the API had
before.

Idempotent: point ids are stable (`point_id_for`), so a rerun overwrites rather
than duplicates, and a game whose collection already has the full point count
is skipped. Resumable with `--checkpoint`: an interrupted run continues from
the last written batch instead of re-embedding.

Usage:
    uv run python scripts/embed/build_text_vector_index.py --game magic
    uv run python scripts/embed/build_text_vector_index.py --game all --dry-run
    uv run python scripts/embed/build_text_vector_index.py --game magic --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "embed") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "embed"))

from payload_backfill import load_rows, payload_for

from ml.search.hybrid_search import (
    _QDRANT_KEYWORD_FIELDS,
    _QDRANT_NUMERIC_FIELDS,
    point_id_for,
)
from ml.utils.paths import PATHS


def cache_paths(game: str, cache_dir: Path, encoder: str) -> tuple[Path, Path]:
    stem = cache_dir / f"text_emb_cache_cards_{game}_{encoder}"
    return stem.with_suffix(".npz"), stem.with_suffix(".names.json")


def load_cache(game: str, cache_dir: Path, encoder: str) -> tuple[list[str], np.ndarray]:
    npz_path, names_path = cache_paths(game, cache_dir, encoder)
    if not npz_path.exists() or not names_path.exists():
        raise SystemExit(f"missing text cache for {game}: {npz_path}")
    names = json.loads(names_path.read_text(encoding="utf-8"))
    matrix = np.load(npz_path)["matrix"].astype(np.float32)
    if matrix.shape[0] != len(names):
        raise SystemExit(
            f"{npz_path.name}: {matrix.shape[0]} rows but {len(names)} names; cache is inconsistent"
        )
    return names, matrix


def connect(url: str):
    from qdrant_client import QdrantClient

    return QdrantClient(url=url)


def ensure_collection(client, collection: str, dim: int) -> str:
    """Create the text collection, or verify an existing one matches.

    Returns "created", "exists" or raises when an existing collection has the
    wrong dimensionality. Deleting is never implicit: pass --force after
    removing it yourself if the encoder changed.
    """
    from qdrant_client import models

    existing = {c.name for c in client.get_collections().collections}
    if collection in existing:
        info = client.get_collection(collection)
        params = info.config.params.vectors
        size = getattr(params, "size", None)
        if isinstance(params, dict):
            size = next(iter(params.values())).size
        if size != dim:
            raise SystemExit(
                f"collection {collection} has vectors of size {size}, expected {dim}; "
                "refusing to reuse it (drop and rebuild deliberately)"
            )
        return "exists"
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        on_disk_payload=True,
    )
    return "created"


def ensure_payload_indexes(client, collection: str) -> None:
    from qdrant_client import models

    for field in sorted(_QDRANT_KEYWORD_FIELDS):
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:  # already exists, or server refuses
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


def payload_lookup(game: str, names: list[str]) -> dict[str, dict[str, Any]]:
    """Typed payload per name; graph-vocabulary names missing from the catalog
    still get a name-only payload so they resolve like they did before."""
    try:
        rows = load_rows(game)
    except SystemExit:
        rows = {}
    payloads: dict[str, dict[str, Any]] = {}
    for name in names:
        row = rows.get(name)
        payloads[name] = payload_for(game, row) if row is not None else {"name": name}
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic", choices=("magic", "pokemon", "yugioh", "all"))
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    parser.add_argument("--data-dir", type=Path, default=PATHS.data)
    parser.add_argument("--cache-dir", type=Path, default=PATHS.data / "cache")
    parser.add_argument("--encoder", default="intfloat-e5-base-v2")
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-upsert every point even when the collection already looks complete",
    )
    parser.add_argument(
        "--checkpoint", type=Path, default=PATHS.processed / ".text_vector_index.json"
    )
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.game == "all" else [args.game]

    checkpoint: dict[str, Any] = {}
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))

    if args.dry_run:
        for game in games:
            names, matrix = load_cache(game, args.cache_dir, args.encoder)
            print(f"{game}: {len(names)} names, {matrix.shape[1]}D, sample {names[:2]}")
        return 0

    from qdrant_client import models

    client = connect(args.url)
    for game in games:
        collection = f"cards_{game}_e5"
        names, matrix = load_cache(game, args.cache_dir, args.encoder)
        dim = int(matrix.shape[1])
        print(f"== {game}: {len(names)} cached names, {dim}D -> {collection}", flush=True)

        state = ensure_collection(client, collection, dim)
        ensure_payload_indexes(client, collection)

        info = client.get_collection(collection)
        if not args.force and state == "exists" and (info.points_count or 0) >= len(names):
            print(
                f"  {collection} already has {info.points_count} points; skipping "
                "(use --force to re-upsert)",
                flush=True,
            )
            continue

        payloads = payload_lookup(game, names)
        start = 0
        if not args.force:
            resume = checkpoint.get(collection, {}).get("next_index")
            if isinstance(resume, int) and 0 < resume <= len(names):
                start = resume
                print(f"  resuming at row {start}", flush=True)

        written = 0
        for begin in range(start, len(names), args.batch):
            chunk = names[begin : begin + args.batch]
            points = [
                models.PointStruct(
                    id=point_id_for(name),
                    vector=matrix[begin + offset].tolist(),
                    payload=payloads[name],
                )
                for offset, name in enumerate(chunk)
            ]
            client.upsert(collection_name=collection, points=points, wait=False)
            written += len(points)
            checkpoint[collection] = {"next_index": begin + len(chunk)}
            args.checkpoint.write_text(json.dumps(checkpoint, indent=1), encoding="utf-8")
            if written % 4096 < args.batch:
                print(f"  upserted {written}/{len(names) - start}", flush=True)

        # Exact count only after the last batch is visible.
        counted = client.count(collection_name=collection, exact=True).count
        checkpoint.pop(collection, None)
        if checkpoint:
            args.checkpoint.write_text(json.dumps(checkpoint, indent=1), encoding="utf-8")
        else:
            args.checkpoint.unlink(missing_ok=True)
        print(
            f"  wrote {written}; collection now reports {counted} points "
            f"({dim}D, ids stable via point_id_for)",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
