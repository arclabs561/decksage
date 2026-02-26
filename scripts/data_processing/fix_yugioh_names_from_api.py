#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Fix Yu-Gi-Oh card names by fetching the full card database from YGOPRODeck API.

Steps:
1. Fetch all cards from https://db.ygoprodeck.com/api/v7/cardinfo.php
2. Build {Card_<id>: actual_name} mapping
3. Save mapping to data/yugioh_card_mapping.json
4. Rewrite pairs CSV in place, replacing Card_IDs with actual names
5. Report mapped vs unmapped counts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
MAPPING_PATH = REPO_ROOT / "data" / "yugioh_card_mapping.json"
PAIRS_CSV = REPO_ROOT / "data" / "processed" / "pairs_yugioh_ygoprodeck-tournament.csv"


def fetch_card_database() -> list[dict]:
    """Fetch the full YGOPRODeck card database."""
    print(f"Fetching card database from {API_URL} ...")
    resp = httpx.get(API_URL, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    cards = data.get("data", [])
    print(f"  Received {len(cards):,} cards from API")
    return cards


def build_mapping(cards: list[dict]) -> dict[str, str]:
    """Build Card_<id> -> actual_name mapping from API response."""
    mapping: dict[str, str] = {}
    for card in cards:
        card_id = card.get("id")
        card_name = card.get("name")
        if card_id is not None and card_name:
            key = f"Card_{card_id}"
            mapping[key] = card_name
    print(f"  Built mapping with {len(mapping):,} entries")
    return mapping


def save_mapping(mapping: dict[str, str], path: Path) -> None:
    """Save mapping to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    print(f"  Saved mapping to {path}")


def rewrite_pairs_csv(csv_path: Path, mapping: dict[str, str]) -> tuple[int, int, int]:
    """Rewrite pairs CSV in place, replacing Card_IDs with actual names.

    Returns (total_ids, mapped, unmapped).
    """
    df = pd.read_csv(csv_path)
    total_ids = 0
    mapped = 0
    unmapped_ids: set[str] = set()

    for col in ("NAME_1", "NAME_2"):
        for idx, val in df[col].items():
            val_str = str(val).strip()
            if val_str.startswith("Card_"):
                total_ids += 1
                if val_str in mapping:
                    df.at[idx, col] = mapping[val_str]
                    mapped += 1
                else:
                    unmapped_ids.add(val_str)

    unmapped = len(unmapped_ids)
    df.to_csv(csv_path, index=False)
    print(f"  Rewrote {csv_path}")
    print(f"  Total Card_ID references: {total_ids:,}")
    print(f"  Successfully mapped:      {mapped:,}")
    print(f"  Unique unmapped IDs:      {unmapped:,}")
    if unmapped_ids:
        sample = sorted(unmapped_ids)[:10]
        print(f"  Sample unmapped: {sample}")
    return total_ids, mapped, unmapped


def main() -> int:
    print("=== Fix Yu-Gi-Oh Card Names from YGOPRODeck API ===\n")

    # Step 1: Fetch
    cards = fetch_card_database()

    # Step 2: Build mapping
    mapping = build_mapping(cards)

    # Step 3: Save mapping
    save_mapping(mapping, MAPPING_PATH)

    # Step 4: Rewrite CSV
    if not PAIRS_CSV.exists():
        print(f"ERROR: Pairs CSV not found at {PAIRS_CSV}")
        return 1
    print(f"\nRewriting {PAIRS_CSV} ...")
    total_ids, mapped, unmapped = rewrite_pairs_csv(PAIRS_CSV, mapping)

    # Step 5: Summary
    pct = (mapped / total_ids * 100) if total_ids else 0
    print("\n=== Summary ===")
    print(f"  API cards fetched:   {len(cards):,}")
    print(f"  Mapping entries:     {len(mapping):,}")
    print(f"  Card_ID refs in CSV: {total_ids:,}")
    print(f"  Mapped successfully: {mapped:,} ({pct:.1f}%)")
    print(f"  Unmapped unique IDs: {unmapped}")

    # Show a sample of the fixed CSV
    print("\n=== Sample rows after fix ===")
    df = pd.read_csv(PAIRS_CSV, nrows=10)
    print(df[["NAME_1", "NAME_2", "COUNT"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
