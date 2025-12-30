#!/usr/bin/env python3
"""
exp_036: Extract ALL Available Signals (Pipeline Improvement)

Deep dive into data extraction to get every signal:
- Archetype labels (format-specific strategies)
- Deck placement (from URL if available)
- Card frequency by archetype
- Card frequency by format
- Temporal data (deck dates)
- Co-occurrence strength
"""

import json
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import zstandard as zstd


def extract_comprehensive_signals():
    """Extract every signal from deck files"""

    print("Extracting ALL signals from deck files...")

    # Find all deck files
    result = subprocess.run(
        ["fd", "-e", "zst", "-t", "f", ".", "data-full/games/magic/mtgtop8/collections"],
        check=False,
        capture_output=True,
        text=True,
        cwd="../backend",
    )

    files = [f for f in result.stdout.strip().split("\n") if f]
    print(f"Processing {len(files)} files...")

    # Signals to extract
    signals = {
        "archetype_cooccurrence": defaultdict(lambda: defaultdict(int)),
        "format_cooccurrence": defaultdict(lambda: defaultdict(int)),
        "card_by_archetype_freq": defaultdict(lambda: defaultdict(int)),
        "card_by_format_freq": defaultdict(lambda: defaultdict(int)),
        "temporal_data": [],
        "deck_metadata": [],
    }

    successful = 0

    for i, filepath in enumerate(files[:500], 1):  # Sample 500
        if i % 50 == 0:
            print(f"  {i}/500...")

        try:
            full_path = Path("../backend") / filepath
            with open(full_path, "rb") as f:
                dctx = zstd.ZstdDecompressor()
                decompressed = dctx.decompress(f.read())
                data = json.loads(decompressed)

            col = data.get("collection", {})

            # Extract deck metadata
            url = col.get("url", "")
            date_str = col.get("release_date", "")
            deck_type = col.get("type", {})

            if isinstance(deck_type, dict):
                inner = deck_type.get("inner", {})
                archetype = inner.get("archetype", "") if isinstance(inner, dict) else ""
                fmt = inner.get("format", "") if isinstance(inner, dict) else ""
                deck_name = inner.get("name", "") if isinstance(inner, dict) else ""
            else:
                archetype = ""
                fmt = ""
                deck_name = ""

            # Extract cards
            cards = []
            for partition in col.get("partitions", []):
                partition.get("name", "Main")
                for card_desc in partition.get("cards", []):
                    card_name = card_desc.get("name")
                    count = card_desc.get("count", 1)
                    if card_name:
                        cards.extend([card_name] * count)

            if not cards:
                continue

            successful += 1

            # Extract temporal
            if date_str:
                try:
                    date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    signals["temporal_data"].append(
                        {
                            "date": date.isoformat(),
                            "cards": cards,
                            "archetype": archetype,
                            "format": fmt,
                        }
                    )
                except:
                    pass

            # Extract archetype signals
            if archetype:
                for i, c1 in enumerate(cards):
                    signals["card_by_archetype_freq"][archetype][c1] += 1

                    for c2 in cards[i + 1 :]:
                        pair = tuple(sorted([c1, c2]))
                        signals["archetype_cooccurrence"][archetype][pair] += 1

            # Extract format signals
            if fmt:
                for i, c1 in enumerate(cards):
                    signals["card_by_format_freq"][fmt][c1] += 1

                    for c2 in cards[i + 1 :]:
                        pair = tuple(sorted([c1, c2]))
                        signals["format_cooccurrence"][fmt][pair] += 1

            # Store metadata
            signals["deck_metadata"].append(
                {
                    "url": url,
                    "archetype": archetype,
                    "format": fmt,
                    "deck_name": deck_name,
                    "num_cards": len(cards),
                    "date": date_str,
                }
            )

        except Exception:
            continue

    print(f"\n✓ Extracted signals from {successful} decks")

    # Analyze
    print("\nSignal Analysis:")
    print(f"  Archetypes found: {len(signals['archetype_cooccurrence'])}")
    print(f"  Formats found: {len(signals['format_cooccurrence'])}")
    print(f"  Temporal decks: {len(signals['temporal_data'])}")

    if signals["archetype_cooccurrence"]:
        print("\n  Top archetypes:")
        arch_sizes = [(a, len(pairs)) for a, pairs in signals["archetype_cooccurrence"].items()]
        for arch, size in sorted(arch_sizes, key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {arch:30s}: {size:6d} pairs")

    if signals["format_cooccurrence"]:
        print("\n  Formats:")
        for fmt, pairs in signals["format_cooccurrence"].items():
            print(f"    {fmt:20s}: {len(pairs):6d} pairs")

    # Save
    import pickle

    with open("../../data/extracted_signals.pkl", "wb") as f:
        pickle.dump(signals, f)

    print("\n✓ Saved all signals to extracted_signals.pkl")

    return signals


if __name__ == "__main__":
    signals = extract_comprehensive_signals()

    print(f"\n{'=' * 60}")
    print("Pipeline Improvement Complete")
    print("=" * 60)
    print("\nNew signals available:")
    print("  • Archetype-specific co-occurrence")
    print("  • Format-specific co-occurrence")
    print("  • Card frequency by archetype/format")
    print("  • Temporal data (when available)")
    print("\nNext experiments can now use these signals!")
