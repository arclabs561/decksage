#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Scrape tournament decklists from YGOProDeck API.

YGOProDeck provides a public API for tournament-topping decks.
This fetches recent competitive decklists and saves them in the
standard deck JSONL format with resolved card names.

Usage:
    .venv/bin/python scripts/data/scrape_ygoprodeck_decks.py \
        --output data/decks/decks_yugioh_ygoprodeck_recent.jsonl \
        --limit 500
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://db.ygoprodeck.com/api/v7"


def fetch_card_db(client: httpx.Client) -> dict[int, str]:
    """Fetch full card database for ID -> name mapping."""
    print("Fetching card database...")
    resp = client.get(f"{BASE_URL}/cardinfo.php", timeout=60)
    resp.raise_for_status()
    data = resp.json()["data"]
    mapping = {}
    for card in data:
        mapping[card["id"]] = card["name"]
    print(f"  {len(mapping)} cards in database")
    return mapping


def fetch_tournament_decks(
    client: httpx.Client,
    card_db: dict[int, str],
    limit: int = 500,
    format_val: str = "TCG",
) -> list[dict]:
    """Fetch tournament-topping decklists."""
    decks = []
    offset = 0
    batch_size = 50  # API max per request

    while len(decks) < limit:
        print(f"  Fetching decks {offset}-{offset + batch_size}...")
        try:
            resp = client.get(
                f"{BASE_URL}/tournament/getRandomDecks.php",
                params={
                    "num": min(batch_size, limit - len(decks)),
                    "offset": offset,
                    "format": format_val,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}, trying alternative endpoint...")
                break

            data = resp.json()
            if not data:
                print("    No more decks available")
                break

            for raw_deck in data:
                deck = _parse_deck(raw_deck, card_db)
                if deck and len(deck["cards"]) >= 20:  # Skip invalid decks
                    decks.append(deck)

            offset += batch_size
            time.sleep(0.5)  # Rate limiting

        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f"    Error: {e}")
            break

    return decks[:limit]


def fetch_decks_by_archetype(
    client: httpx.Client,
    card_db: dict[int, str],
    archetypes: list[str],
    per_archetype: int = 20,
) -> list[dict]:
    """Fetch top decks for specific archetypes."""
    decks = []
    for arch in archetypes:
        print(f"  Fetching {arch} decks...")
        try:
            resp = client.get(
                f"{BASE_URL}/decks/getDecks.php",
                params={
                    "archetype": arch,
                    "num": per_archetype,
                    "sort": "rating",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            if not data:
                continue

            for raw_deck in data:
                deck = _parse_community_deck(raw_deck, card_db, arch)
                if deck and len(deck["cards"]) >= 20:
                    decks.append(deck)

            time.sleep(0.3)

        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f"    Error for {arch}: {e}")
            continue

    return decks


def _parse_deck(raw: dict, card_db: dict[int, str]) -> dict | None:
    """Parse a tournament deck from the API response."""
    try:
        cards = []
        for section in ["main", "extra", "side"]:
            for card_id in raw.get(section, []):
                name = card_db.get(card_id, f"Card_{card_id}")
                partition = {"main": "Main Deck", "extra": "Extra Deck", "side": "Side Deck"}[section]
                # Count duplicates
                existing = next((c for c in cards if c["name"] == name and c["partition"] == partition), None)
                if existing:
                    existing["count"] += 1
                else:
                    cards.append({"name": name, "count": 1, "partition": partition})

        return {
            "cards": cards,
            "source": "ygoprodeck-tournament",
            "format": raw.get("format", "TCG"),
            "event": raw.get("event", ""),
            "placement": raw.get("placement", ""),
            "player": raw.get("player", ""),
            "created_at": raw.get("date", ""),
            "scraped_at": datetime.now().isoformat(),
        }
    except Exception:
        return None


def _parse_community_deck(raw: dict, card_db: dict[int, str], archetype: str) -> dict | None:
    """Parse a community-submitted deck."""
    try:
        cards = []
        for section in ["main_deck", "extra_deck", "side_deck"]:
            for card_str in raw.get(section, "").split("|"):
                if not card_str.strip():
                    continue
                try:
                    card_id = int(card_str.strip())
                    name = card_db.get(card_id, f"Card_{card_id}")
                except ValueError:
                    name = card_str.strip()
                partition = {
                    "main_deck": "Main Deck",
                    "extra_deck": "Extra Deck",
                    "side_deck": "Side Deck",
                }[section]
                existing = next((c for c in cards if c["name"] == name and c["partition"] == partition), None)
                if existing:
                    existing["count"] += 1
                else:
                    cards.append({"name": name, "count": 1, "partition": partition})

        return {
            "cards": cards,
            "source": "ygoprodeck-community",
            "archetype": archetype,
            "deck_name": raw.get("name", ""),
            "rating": raw.get("rating", 0),
            "created_at": raw.get("created_date", ""),
            "scraped_at": datetime.now().isoformat(),
        }
    except Exception:
        return None


# Top competitive archetypes (2025-2026 meta)
TOP_ARCHETYPES = [
    "Snake-Eye", "Tenpai Dragon", "Yubel", "Labrynth", "Branded",
    "Fire King", "Rescue-ACE", "Kashtira", "Purrely", "Runick",
    "Floowandereeze", "Tearlaments", "Spright", "Bystial",
    "Salamangreat", "Sky Striker", "Eldlich", "Tri-Brigade",
    "Virtual World", "Swordsoul", "Despia", "Dragonmaid",
    "Marincess", "Rikka", "Madolche", "Altergeist", "Amazement",
    "Ancient Warriors", "Unchained", "Infernoble Knight",
    "Dragon Link", "Phantom Knights", "Invoked", "Shaddoll",
    "Dogmatika", "Springans", "Therion", "Mathmech",
    "Scareclaw", "Vernusylph", "Naturia", "Centur-Ion",
    "Vaalmonica", "Memento", "White Forest", "Chimera",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape YGO tournament decklists")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--archetypes-only", action="store_true",
                        help="Only fetch by archetype (skip tournament endpoint)")
    parser.add_argument("--per-archetype", type=int, default=20)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        card_db = fetch_card_db(client)

        all_decks = []

        if not args.archetypes_only:
            print("\nFetching tournament decks...")
            tournament = fetch_tournament_decks(client, card_db, limit=args.limit)
            all_decks.extend(tournament)
            print(f"  Got {len(tournament)} tournament decks")

        print(f"\nFetching archetype decks ({len(TOP_ARCHETYPES)} archetypes)...")
        archetype_decks = fetch_decks_by_archetype(
            client, card_db, TOP_ARCHETYPES, per_archetype=args.per_archetype,
        )
        all_decks.extend(archetype_decks)
        print(f"  Got {len(archetype_decks)} archetype decks")

        # Deduplicate by card list
        seen = set()
        unique = []
        for deck in all_decks:
            key = frozenset((c["name"], c["count"]) for c in deck["cards"])
            if key not in seen:
                seen.add(key)
                unique.append(deck)

        print(f"\nTotal: {len(all_decks)} -> {len(unique)} unique decks")

        # Count resolved vs unresolved
        all_cards = set()
        for d in unique:
            for c in d["cards"]:
                all_cards.add(c["name"])
        unresolved = sum(1 for c in all_cards if c.startswith("Card_"))
        print(f"  {len(all_cards)} unique cards, {unresolved} unresolved")

        with open(args.output, "w") as f:
            for deck in unique:
                f.write(json.dumps(deck) + "\n")

        print(f"Written to {args.output}")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
