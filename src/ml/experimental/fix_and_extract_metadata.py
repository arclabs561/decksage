#!/usr/bin/env python3
"""
Fix metadata extraction - bypass dataset cat, read files directly
"""

import json
import subprocess
from collections import defaultdict
from pathlib import Path

import zstandard as zstd


def extract_metadata_directly():
    """Read zstd files directly, bypass broken dataset cat"""

    # Find all MTGTop8 deck files
    result = subprocess.run(
        ["fd", "-e", "zst", "-t", "f", ".", "data-full/games/magic/mtgtop8/collections"],
        check=False,
        capture_output=True,
        text=True,
        cwd="../backend",
    )

    files = result.stdout.strip().split("\n")
    print(f"Found {len(files)} deck files")

    archetypes = defaultdict(int)
    formats = defaultdict(int)
    decks_with_metadata = 0

    for i, filepath in enumerate(files[:1000], 1):  # Sample 1000
        if i % 100 == 0:
            print(f"  Processed {i}...")

        try:
            # Decompress and parse
            full_path = Path("../backend") / filepath
            with open(full_path, "rb") as f:
                dctx = zstd.ZstdDecompressor()
                decompressed = dctx.decompress(f.read())
                data = json.loads(decompressed)

            col = data.get("collection", {})
            deck_type = col.get("type", {})

            # Type can be string or dict
            if isinstance(deck_type, dict):
                inner = deck_type.get("inner", {})
                archetype = inner.get("archetype", "") if isinstance(inner, dict) else ""
                fmt = inner.get("format", "") if isinstance(inner, dict) else ""
            else:
                archetype = ""
                fmt = ""

            if archetype:
                archetypes[archetype] += 1
                decks_with_metadata += 1
            if fmt:
                formats[fmt] += 1

        except Exception as e:
            if i < 5:  # Debug first few
                print(f"  Error on {filepath}: {e}")
            continue

    print(f"\n✓ Extracted metadata from {decks_with_metadata} decks")
    print("\nTop archetypes:")
    for arch, count in sorted(archetypes.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {arch:40s}: {count:4d}")

    print("\nFormats:")
    for fmt, count in sorted(formats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {fmt:20s}: {count:4d}")

    return archetypes, formats


if __name__ == "__main__":
    archetypes, formats = extract_metadata_directly()

    # Save for use in experiments
    with open("../../data/metadata_cache.json", "w") as f:
        json.dump({"archetypes": dict(archetypes), "formats": dict(formats)}, f, indent=2)

    print("\n✓ Saved metadata cache")
