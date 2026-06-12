#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Ingest Scryfall bulk data to enrich Magic card attributes with legality, prices, and mana cost.

Downloads the default_cards bulk export from Scryfall, deduplicates by card name
(keeping the most recent printing), and writes:

  1. data/processed/scryfall_legality.json  -- {card_name: {format: status, ...}}
  2. data/processed/scryfall_prices.json    -- {card_name: {usd: "1.23", ...}}
  3. Updates data/processed/card_attributes_magic_enriched.csv with a mana_cost column.

Usage:
    uv run scripts/data_processing/ingest_scryfall_bulk.py
    uv run scripts/data_processing/ingest_scryfall_bulk.py --skip-download
    uv run scripts/data_processing/ingest_scryfall_bulk.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx


BULK_DATA_API = "https://api.scryfall.com/bulk-data"
BULK_CACHE_PATH = Path("/tmp/scryfall_bulk_cards.json")
USER_AGENT = "DeckSage/1.0 (https://github.com/arclabs561/decksage)"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LEGALITY_OUT = PROCESSED_DIR / "scryfall_legality.json"
PRICES_OUT = PROCESSED_DIR / "scryfall_prices.json"
ENRICHED_CSV = PROCESSED_DIR / "card_attributes_magic_enriched.csv"

# Layouts to skip -- not real playable cards.
SKIP_LAYOUTS = {"art_series", "token", "double_faced_token", "emblem"}

# Price keys to extract.
PRICE_KEYS = ("usd", "usd_foil", "eur", "eur_foil", "tix")


def fetch_bulk_download_uri(client: httpx.Client) -> str:
    """Hit the Scryfall bulk-data endpoint and return the download URI for default_cards."""
    resp = client.get(BULK_DATA_API)
    resp.raise_for_status()
    for entry in resp.json()["data"]:
        if entry["type"] == "default_cards":
            return entry["download_uri"]
    raise ValueError("No 'default_cards' entry found in Scryfall bulk-data response")


def download_bulk_file(client: httpx.Client, url: str, dest: Path) -> None:
    """Stream-download the bulk JSON to disk."""
    print(f"Downloading bulk data from {url}")
    print(f"  -> {dest}")
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(
                        f"\r  {downloaded // (1024 * 1024)}MB / {total // (1024 * 1024)}MB ({pct}%)",
                        end="",
                        flush=True,
                    )
        print()
    print(f"  Download complete: {dest.stat().st_size // (1024 * 1024)}MB")


def front_face_name(name: str) -> str:
    """For DFCs like 'Delver of Secrets // Insectile Aberration', return the front face."""
    return name.split(" // ")[0]


def parse_bulk_cards(path: Path) -> dict[str, dict]:
    """Parse the bulk JSON and deduplicate by card name, keeping the most recent printing.

    Returns {card_name: {legalities, prices, mana_cost, set, released_at}}.
    """
    print(f"Parsing {path} ...")
    with open(path) as f:
        cards = json.load(f)
    print(f"  Loaded {len(cards):,} card objects")

    by_name: dict[str, dict] = {}
    skipped_lang = 0
    skipped_layout = 0

    for card in cards:
        if card.get("lang") != "en":
            skipped_lang += 1
            continue
        if card.get("layout") in SKIP_LAYOUTS:
            skipped_layout += 1
            continue

        name = front_face_name(card.get("name", ""))
        if not name:
            continue

        released_at = card.get("released_at", "")

        # Keep the most recent printing by released_at.
        existing = by_name.get(name)
        if existing and existing["released_at"] >= released_at:
            continue

        # Extract prices, converting nulls to None.
        raw_prices = card.get("prices") or {}
        prices = {k: raw_prices.get(k) for k in PRICE_KEYS}

        by_name[name] = {
            "legalities": card.get("legalities", {}),
            "prices": prices,
            "mana_cost": card.get("mana_cost", ""),
            "set": card.get("set", ""),
            "released_at": released_at,
        }

    print(f"  Unique cards: {len(by_name):,}")
    print(f"  Skipped: {skipped_lang:,} non-English, {skipped_layout:,} art_series/token")
    return by_name


def write_legality(cards: dict[str, dict], dest: Path, *, dry_run: bool) -> None:
    """Write {card_name: {format: status}} JSON."""
    legality = {name: data["legalities"] for name, data in sorted(cards.items())}
    if dry_run:
        sample = dict(list(legality.items())[:3])
        print(f"[dry-run] Would write {len(legality):,} entries to {dest}")
        print(f"  Sample: {json.dumps(sample, indent=2)[:500]}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        json.dump(legality, f, separators=(",", ":"))
    print(f"Wrote {dest} ({dest.stat().st_size // 1024}KB, {len(legality):,} cards)")


def write_prices(cards: dict[str, dict], dest: Path, *, dry_run: bool) -> None:
    """Write {card_name: {usd: "1.23", ...}} JSON."""
    prices = {name: data["prices"] for name, data in sorted(cards.items())}
    if dry_run:
        sample = dict(list(prices.items())[:3])
        print(f"[dry-run] Would write {len(prices):,} entries to {dest}")
        print(f"  Sample: {json.dumps(sample, indent=2)[:500]}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        json.dump(prices, f, separators=(",", ":"))
    print(f"Wrote {dest} ({dest.stat().st_size // 1024}KB, {len(prices):,} cards)")


def update_enriched_csv(cards: dict[str, dict], csv_path: Path, *, dry_run: bool) -> None:
    """Add/update mana_cost column in the magic enriched CSV."""
    if not csv_path.exists():
        print(f"Warning: {csv_path} not found, skipping CSV update")
        return

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    had_mana_cost = "mana_cost" in fieldnames
    if not had_mana_cost:
        fieldnames.append("mana_cost")

    matched = 0
    for row in rows:
        name = row.get("name", "")
        scryfall = cards.get(name)
        if scryfall and scryfall["mana_cost"]:
            row["mana_cost"] = scryfall["mana_cost"]
            matched += 1
        elif "mana_cost" not in row:
            row["mana_cost"] = ""

    print(f"CSV mana_cost merge: {matched:,} / {len(rows):,} rows matched")

    if dry_run:
        print(
            f"[dry-run] Would {'update' if had_mana_cost else 'add'} mana_cost column in {csv_path}"
        )
        return

    out_path = csv_path  # overwrite in place
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated {out_path} ({'updated' if had_mana_cost else 'added'} mana_cost column)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Scryfall bulk data for legality, prices, and mana cost."
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help=f"Reuse previously downloaded bulk file at {BULK_CACHE_PATH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without modifying any files.",
    )
    parser.add_argument(
        "--bulk-file",
        type=Path,
        default=BULK_CACHE_PATH,
        help=f"Path to bulk JSON file (default: {BULK_CACHE_PATH})",
    )
    args = parser.parse_args()

    bulk_path: Path = args.bulk_file

    if not args.skip_download:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        with httpx.Client(headers=headers, follow_redirects=True, timeout=600) as client:
            download_uri = fetch_bulk_download_uri(client)
            # Scryfall asks for max 1 request per 100ms.
            time.sleep(0.1)
            download_bulk_file(client, download_uri, bulk_path)
    else:
        if not bulk_path.exists():
            print(f"Error: --skip-download but {bulk_path} does not exist", file=sys.stderr)
            sys.exit(1)
        print(
            f"Using cached bulk file: {bulk_path} ({bulk_path.stat().st_size // (1024 * 1024)}MB)"
        )

    cards = parse_bulk_cards(bulk_path)

    write_legality(cards, LEGALITY_OUT, dry_run=args.dry_run)
    write_prices(cards, PRICES_OUT, dry_run=args.dry_run)
    update_enriched_csv(cards, ENRICHED_CSV, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[dry-run] No files were modified.")
    else:
        print("\nDone. Outputs:")
        print(f"  {LEGALITY_OUT}")
        print(f"  {PRICES_OUT}")
        print(f"  {ENRICHED_CSV}")


if __name__ == "__main__":
    main()
