#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Scrape Archidekt decks by probing sequential IDs in a recent range.

This supplements the search-based scraper by directly fetching deck details
for a range of recent IDs. Archidekt deck IDs are sequential integers, so
we can probe a contiguous range and filter for Commander-format decks.

Usage:
    uv run scripts/data/scrape_archidekt_sequential.py \
        --output data/decks/decks_magic_commander_seq.jsonl \
        --start-id 20000000 --count 5000 --limit 1000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

USER_AGENT = "DeckSage/1.0 (research project)"
ARCHIDEKT_DECK = "https://archidekt.com/api/decks"
DELAY = 0.5  # faster than search pages -- deck API is more lenient
COMMANDER_FORMAT_IDS = {3, 12, 17, 22, 24}  # Commander, cEDH, Oathbreaker, Brawl, Duel


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _deck_fingerprint(cards: list[dict]) -> str:
    canonical = sorted((c["name"], c["count"], c["partition"]) for c in cards)
    blob = json.dumps(canonical, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def _color_identity_string(colors: list[str] | str | None) -> str:
    if not colors:
        return ""
    if isinstance(colors, str):
        colors = list(colors)
    order = "WUBRG"
    return "".join(c for c in order if c in colors)


def _partition(cat_name: str) -> str:
    lower = cat_name.lower()
    if "commander" in lower or "companion" in lower:
        return "Commander"
    if "side" in lower:
        return "Sideboard"
    if "maybe" in lower:
        return "Maybeboard"
    return "Main"


def _parse_cards(detail: dict) -> list[dict]:
    cards: list[dict] = []
    categories = detail.get("categories", [])
    if categories and isinstance(categories, list):
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            cat_name = cat.get("name", "Main")
            included = cat.get("includedInDeck", cat.get("cards", []))
            if not isinstance(included, list):
                continue
            for entry in included:
                card_info = entry.get("card", entry)
                if not isinstance(card_info, dict):
                    continue
                oracle = card_info.get("oracleCard", card_info)
                name = oracle.get("name", card_info.get("name", ""))
                if not name:
                    continue
                qty = entry.get("quantity", 1)
                cards.append({"name": name, "count": qty, "partition": _partition(cat_name)})
        if cards:
            return cards

    for entry in detail.get("cards", []):
        if not isinstance(entry, dict):
            continue
        card_info = entry.get("card", entry)
        if not isinstance(card_info, dict):
            continue
        oracle = card_info.get("oracleCard", card_info)
        name = oracle.get("name", card_info.get("name", ""))
        if not name:
            continue
        qty = entry.get("quantity", 1)
        categories_list = entry.get("categories", [])
        part = "Main"
        if isinstance(categories_list, list) and categories_list:
            part = _partition(categories_list[0])
        cards.append({"name": name, "count": qty, "partition": part})
    return cards


def _extract_commander(detail: dict, cards: list[dict]) -> str:
    commanders = detail.get("commanders", [])
    if commanders and isinstance(commanders, list):
        names = []
        for cmd in commanders:
            if isinstance(cmd, dict):
                card_info = cmd.get("card", cmd)
                oracle = card_info.get("oracleCard", card_info) if isinstance(card_info, dict) else {}
                n = oracle.get("name", card_info.get("name", "")) if isinstance(oracle, dict) else ""
                if n:
                    names.append(n)
        if names:
            return " / ".join(names)
    cmd_cards = [c["name"] for c in cards if c["partition"] == "Commander"]
    if cmd_cards:
        return " / ".join(cmd_cards)
    return detail.get("name", "Unknown")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Archidekt by sequential ID probing")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-id", type=int, default=20000000, help="Starting deck ID")
    parser.add_argument("--count", type=int, default=5000, help="Number of IDs to probe")
    parser.add_argument("--limit", type=int, default=1000, help="Max decks to collect")
    parser.add_argument("--min-cards", type=int, default=60)
    parser.add_argument("--exclude", type=Path, help="JSONL file of existing decks to skip")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Load existing deck IDs to skip
    existing_ids: set[str] = set()
    existing_fps: set[str] = set()
    if args.exclude and args.exclude.exists():
        with open(args.exclude) as f:
            for line in f:
                d = json.loads(line)
                existing_ids.add(d["deck_id"])
                existing_fps.add(_deck_fingerprint(d["cards"]))
        print(f"Loaded {len(existing_ids)} existing deck IDs to skip")

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    decks: list[dict] = []
    checked = 0
    not_found = 0
    consecutive_404 = 0

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for deck_id in range(args.start_id, args.start_id + args.count):
            if len(decks) >= args.limit:
                break

            did = f"archidekt:{deck_id}"
            if did in existing_ids:
                continue

            checked += 1
            time.sleep(DELAY)

            try:
                resp = client.get(f"{ARCHIDEKT_DECK}/{deck_id}/", timeout=15.0)
            except httpx.HTTPError:
                continue

            if resp.status_code == 404:
                not_found += 1
                consecutive_404 += 1
                if consecutive_404 > 200:
                    print(f"  200+ consecutive 404s at ID {deck_id}, stopping.")
                    break
                continue
            if resp.status_code == 429:
                print(f"  Rate limited at ID {deck_id}, waiting 30s...")
                time.sleep(30)
                continue
            if resp.status_code != 200:
                continue

            consecutive_404 = 0

            try:
                detail = resp.json()
            except (json.JSONDecodeError, ValueError):
                continue

            # Check format
            fmt_id = detail.get("deckFormat", -1)
            if fmt_id not in COMMANDER_FORMAT_IDS:
                continue

            cards = _parse_cards(detail)
            if len(cards) < args.min_cards:
                continue

            fp = _deck_fingerprint(cards)
            if fp in existing_fps:
                continue
            existing_fps.add(fp)

            commander_name = _extract_commander(detail, cards)
            ci = detail.get("colorIdentity", detail.get("color_identity", ""))
            color_id = _color_identity_string(ci if isinstance(ci, list) else list(str(ci)))
            owner = detail.get("owner", {})
            username = owner.get("username", "") if isinstance(owner, dict) else str(owner)
            created = detail.get("createdAt", detail.get("created_at", ""))

            fmt_names = {3: "Commander", 12: "cEDH", 17: "Oathbreaker", 22: "Brawl", 24: "Duel Commander"}
            fmt_name = fmt_names.get(fmt_id, "Commander")

            decks.append({
                "deck_id": did,
                "archetype": commander_name,
                "format": fmt_name,
                "url": f"https://archidekt.com/decks/{deck_id}",
                "source": "archidekt",
                "player": username,
                "event": "",
                "placement": "",
                "commander": commander_name,
                "color_identity": color_id,
                "created_at": created,
                "scraped_at": _now_iso(),
                "cards": cards,
            })

            if len(decks) % 25 == 0:
                print(f"  {len(decks)} decks ({checked} checked, {not_found} 404s)")

    print(f"\nCollected {len(decks)} decks from {checked} probed IDs ({not_found} not found)")

    with open(args.output, "w") as f:
        for deck in decks:
            f.write(json.dumps(deck) + "\n")

    print(f"Written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
