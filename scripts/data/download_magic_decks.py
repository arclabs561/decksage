#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["zstandard", "boto3"]
# ///
"""
Download Magic deck data from S3 and convert to JSONL format.

Uses s5cmd for fast parallel downloads, falls back to boto3.
Processes .zst compressed deck files into the standard JSONL format
used by extract_card_sets_fast.py.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/data/download_magic_decks.py \
    --source goldfish \
    --output data/decks/decks_magic_goldfish.jsonl \
    --limit 10000

  # All sources:
  PYTHONPATH=src .venv/bin/python scripts/data/download_magic_decks.py \
    --source goldfish mtgtop8 \
    --output data/decks/decks_magic.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zstandard


S3_BUCKET = "games-collections"
S3_SOURCES = {
    "goldfish": f"s3://{S3_BUCKET}/games/magic/goldfish/",
    "mtgtop8": f"s3://{S3_BUCKET}/games/magic/mtgtop8/collections/",
    "deckbox": f"s3://{S3_BUCKET}/games/magic/deckbox/",
}


def list_s3_files(prefix: str, limit: int | None = None) -> list[str]:
    """List .zst files in S3 prefix using aws cli."""
    cmd = ["aws", "s3", "ls", prefix, "--recursive"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  Warning: aws s3 ls failed: {result.stderr[:200]}", file=sys.stderr)
        return []

    files = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[-1].endswith(".zst"):
            key = parts[-1]
            files.append(f"s3://{S3_BUCKET}/{key}")
    if limit:
        files = files[:limit]
    return files


def download_batch_s5cmd(s3_urls: list[str], dest_dir: Path) -> int:
    """Download files using s5cmd (fast parallel)."""
    # Write URL list to temp file
    url_file = dest_dir / "_urls.txt"
    with open(url_file, "w") as f:
        for url in s3_urls:
            f.write(f"cp {url} {dest_dir}/\n")

    cmd = ["s5cmd", "--log", "error", "run", str(url_file)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    url_file.unlink(missing_ok=True)

    if result.returncode != 0 and result.stderr:
        print(f"  s5cmd warnings: {result.stderr[:200]}", file=sys.stderr)

    return len(list(dest_dir.glob("*.zst")))


def download_batch_awscli(s3_urls: list[str], dest_dir: Path) -> int:
    """Download files using aws s3 cp (slower fallback)."""
    downloaded = 0
    for url in s3_urls:
        filename = url.split("/")[-1]
        dest = dest_dir / filename
        result = subprocess.run(
            ["aws", "s3", "cp", url, str(dest)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            downloaded += 1
    return downloaded


def process_deck_file(path: Path, source: str) -> dict | None:
    """Read a .zst deck file and convert to standard JSONL format."""
    try:
        dctx = zstandard.ZstdDecompressor()
        with open(path, "rb") as f:
            reader = dctx.stream_reader(f)
            data = json.load(reader)
    except Exception:
        return None

    # Extract deck info
    deck_id = data.get("id", path.stem)
    url = data.get("url", "")
    type_info = data.get("type", {})
    deck_type = type_info.get("type", "")

    # Skip non-deck collections (Sets, Cubes)
    if deck_type in ("Set", "Cube"):
        return None

    inner = type_info.get("inner", {})
    archetype = inner.get("name", "")
    fmt = inner.get("format", "")

    # Extract cards from main partition only (skip sideboard)
    cards = []
    for partition in data.get("partitions", []):
        part_name = partition.get("name", "Main")
        for card in partition.get("cards", []):
            cards.append({
                "name": card["name"],
                "count": card.get("count", 1),
                "partition": part_name,
            })

    if not cards:
        return None

    return {
        "deck_id": deck_id,
        "archetype": archetype,
        "format": fmt,
        "url": url,
        "source": source,
        "player": "",
        "event": "",
        "placement": "",
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Magic decks from S3")
    parser.add_argument(
        "--source", nargs="+", default=["goldfish"],
        choices=list(S3_SOURCES.keys()),
        help="S3 data sources to download from",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--limit", type=int, help="Max decks per source")
    parser.add_argument("--batch-size", type=int, default=5000, help="Download batch size")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    use_s5cmd = shutil.which("s5cmd") is not None

    total_decks = 0
    total_skipped = 0

    with open(args.output, "w") as out_f:
        for source in args.source:
            prefix = S3_SOURCES[source]
            print(f"\n{'='*60}")
            print(f"Source: {source} ({prefix})")
            print(f"{'='*60}")

            # List files
            print("  Listing S3 files...")
            t0 = time.monotonic()
            s3_files = list_s3_files(prefix, limit=args.limit)
            print(f"  Found {len(s3_files):,} .zst files ({time.monotonic() - t0:.1f}s)")

            if not s3_files:
                print("  No files found, skipping.")
                continue

            # Process in batches
            source_decks = 0
            source_skipped = 0

            for batch_start in range(0, len(s3_files), args.batch_size):
                batch = s3_files[batch_start : batch_start + args.batch_size]
                batch_num = batch_start // args.batch_size + 1
                total_batches = (len(s3_files) + args.batch_size - 1) // args.batch_size

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    print(f"\n  Batch {batch_num}/{total_batches}: downloading {len(batch)} files...")
                    t0 = time.monotonic()

                    if use_s5cmd:
                        downloaded = download_batch_s5cmd(batch, tmp_path)
                    else:
                        downloaded = download_batch_awscli(batch, tmp_path)

                    dl_time = time.monotonic() - t0
                    print(f"    Downloaded {downloaded} files in {dl_time:.1f}s")

                    # Process downloaded files
                    for zst_file in sorted(tmp_path.glob("*.zst")):
                        deck = process_deck_file(zst_file, source)
                        if deck:
                            out_f.write(json.dumps(deck) + "\n")
                            source_decks += 1
                        else:
                            source_skipped += 1

                    print(f"    Processed: {source_decks} decks (+{source_skipped} skipped)")

            total_decks += source_decks
            total_skipped += source_skipped
            print(f"\n  {source} total: {source_decks:,} decks, {source_skipped:,} skipped")

    print(f"\n{'='*60}")
    print(f"DONE: {total_decks:,} decks written to {args.output}")
    print(f"  ({total_skipped:,} non-deck collections skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
