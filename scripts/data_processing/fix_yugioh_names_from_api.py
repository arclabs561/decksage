#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Fix Yu-Gi-Oh card names by replacing Card_XXXX IDs with actual card names.

Targets:
- All data/processed/pairs_yugioh_*.csv files (NAME_1/NAME_2 columns)
- data/graphs/yugioh_unified.edg (tab-separated edgelist)

Steps:
1. Load mapping from data/yugioh_card_mapping.json (or fetch from YGOPRODeck API)
2. For each pairs CSV: replace Card_IDs in NAME_1/NAME_2 columns
3. For the edgelist: replace Card_IDs in node1/node2 fields
4. Drop edges/rows where EITHER node is an unresolvable Card_XXXX ID
5. Report before/after counts per file
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
MAPPING_PATH = REPO_ROOT / "data" / "yugioh_card_mapping.json"
PAIRS_DIR = REPO_ROOT / "data" / "processed"
EDGELIST_PATH = REPO_ROOT / "data" / "graphs" / "yugioh_unified.edg"
MERGED_EDGELIST_PATH = REPO_ROOT / "data" / "graphs" / "yugioh_merged_all.edg"

CARD_ID_RE = re.compile(r"^Card_\d+$")


def load_or_fetch_mapping() -> dict[str, str]:
    """Load mapping from disk; fetch from API only if missing."""
    if MAPPING_PATH.exists():
        print(f"Loading existing mapping from {MAPPING_PATH} ...")
        with open(MAPPING_PATH) as f:
            mapping = json.load(f)
        print(f"  Loaded {len(mapping):,} entries")
        return mapping

    print(f"No mapping file at {MAPPING_PATH}, fetching from API ...")
    return fetch_and_save_mapping()


def fetch_and_save_mapping() -> dict[str, str]:
    """Fetch the full YGOPRODeck card database and save mapping."""
    print(f"Fetching card database from {API_URL} ...")
    try:
        resp = httpx.get(API_URL, timeout=60.0)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f"  API fetch failed: {e}")
        if MAPPING_PATH.exists():
            print(f"  Falling back to existing mapping at {MAPPING_PATH}")
            with open(MAPPING_PATH) as f:
                return json.load(f)
        print("  ERROR: No mapping available. Cannot proceed.")
        sys.exit(1)

    data = resp.json()
    cards = data.get("data", [])
    print(f"  Received {len(cards):,} cards from API")

    mapping: dict[str, str] = {}
    for card in cards:
        card_id = card.get("id")
        card_name = card.get("name")
        if card_id is not None and card_name:
            mapping[f"Card_{card_id}"] = card_name
    print(f"  Built mapping with {len(mapping):,} entries")

    MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    print(f"  Saved mapping to {MAPPING_PATH}")
    return mapping


def resolve_name(name: str, mapping: dict[str, str]) -> str | None:
    """Resolve a Card_XXXX name. Returns resolved name, original if not Card_, or None if unresolvable."""
    name = name.strip()
    if not CARD_ID_RE.match(name):
        return name
    return mapping.get(name)


def rewrite_pairs_csv(csv_path: Path, mapping: dict[str, str]) -> dict:
    """Rewrite a pairs CSV, replacing Card_IDs with actual names.

    Drops rows where EITHER NAME_1 or NAME_2 is an unresolvable Card_ID.
    Returns stats dict.
    """
    df = pd.read_csv(csv_path)
    rows_before = len(df)
    total_ids = 0
    mapped = 0
    unmapped_ids: set[str] = set()

    for col in ("NAME_1", "NAME_2"):
        for idx, val in df[col].items():
            val_str = str(val).strip()
            if CARD_ID_RE.match(val_str):
                total_ids += 1
                if val_str in mapping:
                    df.at[idx, col] = mapping[val_str]
                    mapped += 1
                else:
                    unmapped_ids.add(val_str)

    # Drop rows where EITHER column is still an unresolvable Card_ID
    mask_1 = df["NAME_1"].apply(lambda x: bool(CARD_ID_RE.match(str(x).strip())))
    mask_2 = df["NAME_2"].apply(lambda x: bool(CARD_ID_RE.match(str(x).strip())))
    any_unresolved = mask_1 | mask_2
    dropped = any_unresolved.sum()
    df = df[~any_unresolved]

    rows_after = len(df)
    df.to_csv(csv_path, index=False)

    stats = {
        "file": csv_path.name,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "dropped": dropped,
        "total_card_ids": total_ids,
        "mapped": mapped,
        "unmapped_unique": len(unmapped_ids),
        "unmapped_ids": sorted(unmapped_ids),
    }
    return stats


def rewrite_edgelist(edg_path: Path, mapping: dict[str, str]) -> dict:
    """Rewrite the tab-separated edgelist, replacing Card_IDs in node names.

    Format: node1<TAB>node2<TAB>weight
    Node names may be quoted with double-quotes.

    Drops edges where EITHER node is still an unresolvable Card_XXXX ID.
    """
    lines_before = 0
    lines_after = 0
    total_ids = 0
    mapped = 0
    dropped = 0
    unmapped_ids: set[str] = set()

    output_lines: list[str] = []

    with open(edg_path) as f:
        for line in f:
            lines_before += 1
            line = line.rstrip("\n")
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 3:
                output_lines.append(line)
                lines_after += 1
                continue

            node1, node2, weight = parts[0], parts[1], parts[2]

            # Strip outer quotes if present (the edgelist quotes names with internal quotes)
            def strip_outer_quotes(s: str) -> str:
                if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                    return s[1:-1]
                return s

            raw1 = strip_outer_quotes(node1)
            raw2 = strip_outer_quotes(node2)

            resolved1 = raw1
            resolved2 = raw2

            if CARD_ID_RE.match(raw1):
                total_ids += 1
                if raw1 in mapping:
                    resolved1 = mapping[raw1]
                    mapped += 1
                else:
                    unmapped_ids.add(raw1)

            if CARD_ID_RE.match(raw2):
                total_ids += 1
                if raw2 in mapping:
                    resolved2 = mapping[raw2]
                    mapped += 1
                else:
                    unmapped_ids.add(raw2)

            # Drop if EITHER node is still an unresolvable Card_ID
            still_card_1 = CARD_ID_RE.match(resolved1)
            still_card_2 = CARD_ID_RE.match(resolved2)
            if still_card_1 or still_card_2:
                dropped += 1
                continue

            # Write names without outer quotes -- the training scripts parse
            # edgelists by tab-split, so internal quotes/commas are safe.
            out_line = f"{resolved1}\t{resolved2}\t{weight}"
            output_lines.append(out_line)
            lines_after += 1

    with open(edg_path, "w") as f:
        f.write("\n".join(output_lines))
        if output_lines:
            f.write("\n")

    stats = {
        "file": edg_path.name,
        "lines_before": lines_before,
        "lines_after": lines_after,
        "dropped": dropped,
        "total_card_ids": total_ids,
        "mapped": mapped,
        "unmapped_unique": len(unmapped_ids),
        "unmapped_ids": sorted(unmapped_ids),
    }
    return stats


def count_remaining_card_ids(path: Path) -> int:
    """Count remaining Card_XXXX references in a file."""
    count = 0
    with open(path) as f:
        for line in f:
            count += len(CARD_ID_RE.findall(line))
    return count


def main() -> int:
    print("=== Fix Yu-Gi-Oh Card_XXXX IDs Across All Data Files ===\n")

    # Step 1: Load mapping
    mapping = load_or_fetch_mapping()

    all_stats: list[dict] = []

    # Step 2: Fix all pairs CSVs
    csv_files = sorted(PAIRS_DIR.glob("pairs_yugioh_*.csv"))
    if not csv_files:
        print("WARNING: No pairs_yugioh_*.csv files found")
    else:
        print(f"\nFound {len(csv_files)} pairs CSV files to fix:")
        for csv_path in csv_files:
            print(f"\n--- {csv_path.name} ---")
            stats = rewrite_pairs_csv(csv_path, mapping)
            all_stats.append(stats)
            print(
                f"  Rows:     {stats['rows_before']:>8,} -> {stats['rows_after']:>8,} (dropped {stats['dropped']:,})"
            )
            print(
                f"  Card_IDs: {stats['total_card_ids']:>8,} found, {stats['mapped']:,} mapped, {stats['unmapped_unique']} unique unmapped"
            )
            if stats["unmapped_ids"]:
                print(f"  Unmapped: {stats['unmapped_ids'][:10]}")

    # Step 3: Fix edgelists (unified + merged_all used by training)
    for edg_path in [EDGELIST_PATH, MERGED_EDGELIST_PATH]:
        if edg_path.exists():
            print(f"\n--- {edg_path.name} ---")
            stats = rewrite_edgelist(edg_path, mapping)
            all_stats.append(stats)
            print(
                f"  Lines:    {stats['lines_before']:>10,} -> {stats['lines_after']:>10,} (dropped {stats['dropped']:,})"
            )
            print(
                f"  Card_IDs: {stats['total_card_ids']:>10,} found, {stats['mapped']:,} mapped, {stats['unmapped_unique']} unique unmapped"
            )
            if stats["unmapped_ids"]:
                print(f"  Unmapped: {stats['unmapped_ids'][:10]}")
        else:
            print(f"\nWARNING: Edgelist not found at {edg_path}")

    # Step 4: Verification -- count remaining Card_ entries
    print("\n=== Verification: Remaining Card_XXXX References ===")
    total_remaining = 0
    for path in [*csv_files, EDGELIST_PATH, MERGED_EDGELIST_PATH]:
        if path.exists():
            remaining = count_remaining_card_ids(path)
            total_remaining += remaining
            status = "CLEAN" if remaining == 0 else f"{remaining:,} remaining"
            print(f"  {path.name}: {status}")

    # Step 5: Summary
    print("\n=== Summary ===")
    print(f"  Mapping entries:     {len(mapping):,}")
    total_mapped = sum(s.get("mapped", 0) for s in all_stats)
    total_dropped = sum(s.get("dropped", 0) for s in all_stats)
    total_found = sum(s.get("total_card_ids", 0) for s in all_stats)
    print(f"  Total Card_IDs found:  {total_found:,}")
    print(f"  Successfully mapped:   {total_mapped:,}")
    print(f"  Edges/rows dropped:    {total_dropped:,}")
    print(f"  Remaining Card_XXXX:   {total_remaining:,}")

    # Collect all unmapped IDs across all files
    all_unmapped: set[str] = set()
    for s in all_stats:
        all_unmapped.update(s.get("unmapped_ids", []))
    if all_unmapped:
        print(f"\n  Truly unresolvable IDs ({len(all_unmapped)}):")
        for uid in sorted(all_unmapped):
            print(f"    {uid}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
