#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["zstandard"]
# ///
"""
Backfill created_at timestamps for existing Magic Goldfish decks.

Downloads raw .zst files from S3 in batches, extracts release_date,
and patches the existing JSONL file.

Usage:
  uv run scripts/data/backfill_magic_timestamps.py \
    --input data/decks/decks_magic_goldfish.jsonl \
    --output data/decks/decks_magic_goldfish_ts.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zstandard


S3_PREFIX = "s3://games-collections/games/magic/goldfish/"
BATCH_SIZE = 5000


def list_s3_files() -> list[str]:
    """List all .zst files in the goldfish S3 prefix."""
    cmd = ["aws", "s3", "ls", S3_PREFIX, "--recursive"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"Error listing S3: {result.stderr[:200]}", file=sys.stderr)
        return []
    files = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[-1].endswith(".zst"):
            files.append(f"s3://games-collections/{parts[-1]}")
    return files


def extract_dates_from_batch(s3_urls: list[str]) -> dict[str, str]:
    """Download a batch of .zst files and extract deck_id -> release_date mapping."""
    mapping = {}
    dctx = zstandard.ZstdDecompressor()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Try s5cmd first, fall back to aws cli
        import shutil

        if shutil.which("s5cmd"):
            url_file = tmp_path / "_urls.txt"
            with open(url_file, "w") as f:
                for url in s3_urls:
                    f.write(f"cp {url} {tmp_path}/\n")
            subprocess.run(
                ["s5cmd", "--log", "error", "run", str(url_file)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            url_file.unlink(missing_ok=True)
        else:
            for url in s3_urls:
                fname = url.split("/")[-1]
                subprocess.run(
                    ["aws", "s3", "cp", url, str(tmp_path / fname)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

        for zst_file in tmp_path.glob("*.zst"):
            try:
                with open(zst_file, "rb") as f:
                    data = json.load(dctx.stream_reader(f))
                deck_id = data.get("id", zst_file.stem)
                # Extract release_date
                for key in ("event_date", "date", "created_at", "release_date"):
                    val = (data.get(key) or "").strip()
                    if val:
                        mapping[deck_id] = val[:10]  # date-only
                        break
            except Exception:
                continue

    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Magic deck timestamps")
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    # Step 1: List S3 files
    print("Listing S3 files...")
    t0 = time.monotonic()
    s3_files = list_s3_files()
    print(f"  Found {len(s3_files):,} files ({time.monotonic() - t0:.1f}s)")

    if not s3_files:
        print("No S3 files found. Cannot backfill.", file=sys.stderr)
        return 1

    # Step 2: Download and extract dates in batches
    print("\nExtracting dates from raw files...")
    date_map: dict[str, str] = {}
    total_batches = (len(s3_files) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(s3_files), BATCH_SIZE):
        batch = s3_files[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        t0 = time.monotonic()
        batch_dates = extract_dates_from_batch(batch)
        date_map.update(batch_dates)
        elapsed = time.monotonic() - t0
        print(
            f"  Batch {batch_num}/{total_batches}: {len(batch_dates)} dates ({elapsed:.1f}s) | total: {len(date_map):,}"
        )

    print(f"\nExtracted {len(date_map):,} dates from S3")

    # Step 3: Patch the JSONL
    print(f"\nPatching {args.input} -> {args.output}...")
    total = 0
    added = 0
    already_had = 0
    no_match = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.input) as inf, open(args.output, "w") as outf:
        for line in inf:
            total += 1
            rec = json.loads(line)

            if rec.get("created_at"):
                already_had += 1
                outf.write(line)
                continue

            deck_id = rec.get("deck_id", "")
            # Try both with and without "deck:" prefix
            date = date_map.get(deck_id) or date_map.get(f"deck:{deck_id}")
            if date:
                rec["created_at"] = date
                added += 1
                outf.write(json.dumps(rec) + "\n")
            else:
                no_match += 1
                outf.write(line)

    print("\nResults:")
    print(f"  Total decks:       {total:,}")
    print(f"  Already had date:  {already_had:,}")
    print(f"  Dates added:       {added:,}")
    print(f"  No date found:     {no_match:,}")
    print(f"  Coverage:          {(already_had + added) / total * 100:.1f}%")
    print(f"\nOutput: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
