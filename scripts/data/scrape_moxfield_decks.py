#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax"]
# ///
"""
Scrape Commander/EDH decklists from Moxfield and Archidekt APIs.

Both APIs are unofficial/reverse-engineered. Archidekt's is more accessible;
Moxfield's is behind Cloudflare and may reject automated requests.
The script handles Moxfield failures gracefully and continues with Archidekt.

Output: standard deck JSONL format (one JSON object per line).

Usage:
    uv run scripts/data/scrape_moxfield_decks.py \
        --output data/decks/decks_magic_commander_edh.jsonl \
        --limit 5000

    uv run scripts/data/scrape_moxfield_decks.py \
        --output data/decks/decks_magic_commander_archidekt.jsonl \
        --source archidekt --limit 3000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "DeckSage/1.0 (research project)"

# Moxfield
MOXFIELD_BASE = "https://api2.moxfield.com"
MOXFIELD_SEARCH = f"{MOXFIELD_BASE}/v3/decks/search"
MOXFIELD_DECK = f"{MOXFIELD_BASE}/v2/decks/all"  # /{publicId}
MOXFIELD_DELAY = 1.0  # seconds between requests

# Archidekt  (format=3 is Commander)
# The listing endpoint (/api/decks/v3/) was removed. Instead, scrape deck IDs
# from the server-rendered search page and fetch each via /api/decks/{id}/.
ARCHIDEKT_SEARCH_URL = "https://archidekt.com/search/decks"
ARCHIDEKT_DECK = "https://archidekt.com/api/decks"  # /{id}/
ARCHIDEKT_DELAY = 0.5

MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _deck_fingerprint(cards: list[dict]) -> str:
    """Deterministic hash of a card list for deduplication."""
    canonical = sorted((c["name"], c["count"], c["partition"]) for c in cards)
    blob = json.dumps(canonical, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    max_retries: int = MAX_RETRIES,
    timeout: float = 30.0,
) -> httpx.Response | None:
    """Issue an HTTP request with exponential backoff.

    Returns None if all retries are exhausted or the server returns
    a non-retryable status (403, 404).
    """
    backoff = INITIAL_BACKOFF
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.request(method, url, params=params, timeout=timeout)
            if resp.status_code in (403, 404):
                # Not retryable
                return resp
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"    HTTP {resp.status_code} on attempt {attempt}, backing off {backoff:.1f}s")
                time.sleep(backoff)
                backoff *= 2
                continue
            return resp
        except httpx.HTTPError as exc:
            print(f"    Network error on attempt {attempt}: {exc}")
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                return None
    return None


def _color_identity_string(colors: list[str] | str | None) -> str:
    """Normalize color identity to a WUBRG-ordered string."""
    if not colors:
        return ""
    if isinstance(colors, str):
        colors = list(colors)
    order = "WUBRG"
    return "".join(c for c in order if c in colors)


# ---------------------------------------------------------------------------
# Archidekt
# ---------------------------------------------------------------------------


def _scrape_archidekt_deck_ids(
    client: httpx.Client,
    limit: int,
) -> list[int]:
    """Scrape deck IDs from Archidekt's server-rendered search page.

    The listing API (/api/decks/v3/) was removed. The search page at
    /search/decks still renders deck links server-side, so we extract
    IDs from href="/decks/{id}" patterns.
    """
    seen: set[int] = set()
    page = 1
    consecutive_empty = 0

    while len(seen) < limit:
        params = {"formats": "3", "orderBy": "-viewCount", "page": str(page)}
        resp = _request_with_retry(
            client, "GET", ARCHIDEKT_SEARCH_URL, params=params, timeout=30.0
        )
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp else "no response"
            print(f"  Search page {page} failed (status={status}), stopping ID scan.")
            break

        tree = HTMLParser(resp.text)
        ids_on_page: list[int] = []
        for node in tree.css("a[href]"):
            href = node.attributes.get("href", "")
            m = re.match(r"/decks/(\d+)", href)
            if m:
                deck_id = int(m.group(1))
                if deck_id not in seen:
                    ids_on_page.append(deck_id)
                    seen.add(deck_id)

        if not ids_on_page:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
            page += 1
            continue

        consecutive_empty = 0
        print(f"  Page {page}: found {len(ids_on_page)} new deck IDs (total: {len(seen)})")
        page += 1
        time.sleep(ARCHIDEKT_DELAY)

    return list(seen)[:limit]


def scrape_archidekt(
    client: httpx.Client,
    limit: int,
    min_cards: int,
) -> list[dict]:
    """Scrape Commander decklists from Archidekt.

    Strategy:
    1. Scrape deck IDs from the search HTML page (sorted by view count).
    2. For each deck, fetch full detail via /api/decks/{id}/.
    """
    print(f"[archidekt] Scraping up to {limit} decks...")
    print("  Phase 1: discovering deck IDs from search page...")
    deck_ids = _scrape_archidekt_deck_ids(client, limit)
    print(f"  Found {len(deck_ids)} deck IDs.")

    print("  Phase 2: fetching deck details...")
    decks: list[dict] = []
    for i, deck_id in enumerate(deck_ids):
        if len(decks) >= limit:
            break

        time.sleep(ARCHIDEKT_DELAY)
        detail = _fetch_archidekt_deck(client, deck_id)
        if detail is None:
            continue

        cards = _parse_archidekt_cards(detail)
        if len(cards) < min_cards:
            continue

        commander_name = _extract_archidekt_commander(detail, cards)
        color_id = _archidekt_color_identity(detail, cards)
        owner = detail.get("owner", {})
        username = owner.get("username", "") if isinstance(owner, dict) else str(owner)
        created = detail.get("createdAt", detail.get("created_at", ""))

        decks.append({
            "deck_id": f"archidekt:{deck_id}",
            "archetype": commander_name,
            "format": "Commander",
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

        if len(decks) % 25 == 0 or i == len(deck_ids) - 1:
            print(f"  {len(decks)} decks collected ({i + 1}/{len(deck_ids)} checked)...")

    print(f"[archidekt] Collected {len(decks)} decks.")
    return decks


def _fetch_archidekt_deck(client: httpx.Client, deck_id: int) -> dict | None:
    url = f"{ARCHIDEKT_DECK}/{deck_id}/"
    resp = _request_with_retry(client, "GET", url)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_archidekt_cards(detail: dict) -> list[dict]:
    """Extract card list from Archidekt deck detail.

    Archidekt uses a `categories` list, each containing `includedInDeck`
    cards, or a flat `cards` list depending on API version.
    """
    cards: list[dict] = []

    # Try categories-based structure first
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
                partition = _archidekt_partition(cat_name)
                cards.append({"name": name, "count": qty, "partition": partition})
        if cards:
            return cards

    # Flat cards list fallback
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
        partition = "Main"
        if isinstance(categories_list, list) and categories_list:
            partition = _archidekt_partition(categories_list[0])
        cards.append({"name": name, "count": qty, "partition": partition})

    return cards


def _archidekt_partition(cat_name: str) -> str:
    """Map Archidekt category name to our partition names."""
    lower = cat_name.lower()
    if "commander" in lower or "companion" in lower:
        return "Commander"
    if "side" in lower:
        return "Sideboard"
    if "maybe" in lower:
        return "Maybeboard"
    return "Main"


def _extract_archidekt_commander(detail: dict, cards: list[dict]) -> str:
    """Extract commander name from deck detail or card partitions."""
    # Check deck-level commander info
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
            elif isinstance(cmd, str):
                names.append(cmd)
        if names:
            return " / ".join(names)

    # Fall back to cards with Commander partition
    cmd_cards = [c["name"] for c in cards if c["partition"] == "Commander"]
    if cmd_cards:
        return " / ".join(cmd_cards)

    return detail.get("name", "Unknown")


def _archidekt_color_identity(detail: dict, cards: list[dict]) -> str:
    """Extract color identity from deck detail."""
    # Try deck-level color identity
    ci = detail.get("colorIdentity", detail.get("color_identity", ""))
    if ci:
        if isinstance(ci, list):
            return _color_identity_string(ci)
        return _color_identity_string(str(ci))
    return ""


# ---------------------------------------------------------------------------
# Moxfield
# ---------------------------------------------------------------------------


def scrape_moxfield(
    client: httpx.Client,
    limit: int,
    min_cards: int,
) -> list[dict]:
    """Scrape Commander decklists from Moxfield.

    Moxfield is behind Cloudflare and may block automated requests.
    This function handles failures gracefully and returns whatever
    it managed to collect (possibly zero).
    """
    decks: list[dict] = []
    page = 1

    print(f"[moxfield] Scraping up to {limit} decks (may fail due to Cloudflare)...")

    # Probe first page to see if we can access the API at all
    probe_resp = _request_with_retry(
        client, "GET", MOXFIELD_SEARCH,
        params={"fmt": "commander", "pageSize": "1", "pageNumber": "1"},
    )
    if probe_resp is None or probe_resp.status_code in (403, 503):
        status = probe_resp.status_code if probe_resp else "no response"
        print(f"  Moxfield API is not accessible (status={status}). "
              "This is expected -- Cloudflare blocks automated requests.")
        print("  Skipping Moxfield. Use --source archidekt to avoid this message.")
        return []

    while len(decks) < limit:
        params = {
            "fmt": "commander",
            "sortType": "views",
            "sortDirection": "Descending",
            "pageNumber": str(page),
            "pageSize": "64",
        }
        resp = _request_with_retry(client, "GET", MOXFIELD_SEARCH, params=params)
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp else "no response"
            print(f"  Search page {page} failed (status={status}), stopping.")
            break

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            print(f"  Invalid JSON on page {page}, stopping.")
            break

        # Moxfield wraps results in a 'data' key
        results = data.get("data", data.get("results", []))
        if not results:
            print("  No more results from Moxfield.")
            break

        for item in results:
            if len(decks) >= limit:
                break

            public_id = item.get("publicId")
            if not public_id:
                continue

            time.sleep(MOXFIELD_DELAY)
            detail = _fetch_moxfield_deck(client, public_id)
            if detail is None:
                continue

            cards = _parse_moxfield_cards(detail)
            if len(cards) < min_cards:
                continue

            commander_name = _extract_moxfield_commander(detail, cards)
            color_id = _color_identity_string(
                detail.get("colorIdentity", detail.get("colors", []))
            )
            created = detail.get("createdAtUtc", item.get("createdAtUtc", ""))
            username = (
                detail.get("createdByUser", {}).get("userName", "")
                or item.get("createdByUser", {}).get("userName", "")
            )

            decks.append({
                "deck_id": f"moxfield:{public_id}",
                "archetype": commander_name,
                "format": "Commander",
                "url": f"https://www.moxfield.com/decks/{public_id}",
                "source": "moxfield",
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
                print(f"  {len(decks)} decks collected...")

        page += 1
        time.sleep(MOXFIELD_DELAY)

    print(f"[moxfield] Collected {len(decks)} decks.")
    return decks


def _fetch_moxfield_deck(client: httpx.Client, public_id: str) -> dict | None:
    url = f"{MOXFIELD_DECK}/{public_id}"
    resp = _request_with_retry(client, "GET", url)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_moxfield_cards(detail: dict) -> list[dict]:
    """Extract card list from Moxfield deck detail.

    Moxfield deck detail has top-level keys: mainboard, sideboard,
    commanders, companions, etc. Each is a dict mapping card name
    to card info with a `quantity` field.
    """
    cards: list[dict] = []
    section_map = {
        "commanders": "Commander",
        "companions": "Commander",
        "mainboard": "Main",
        "sideboard": "Sideboard",
        "maybeboard": "Maybeboard",
    }

    for section_key, partition in section_map.items():
        section = detail.get(section_key, {})
        if not isinstance(section, dict):
            continue
        for card_key, card_data in section.items():
            if not isinstance(card_data, dict):
                continue
            # card_data has 'card' (card info) and 'quantity'
            inner = card_data.get("card", {})
            name = inner.get("name", card_key) if isinstance(inner, dict) else card_key
            qty = card_data.get("quantity", 1)
            if name:
                cards.append({"name": name, "count": qty, "partition": partition})

    return cards


def _extract_moxfield_commander(detail: dict, cards: list[dict]) -> str:
    """Extract commander name from Moxfield deck detail."""
    commanders = detail.get("commanders", {})
    if isinstance(commanders, dict) and commanders:
        names = []
        for card_data in commanders.values():
            if isinstance(card_data, dict):
                inner = card_data.get("card", {})
                name = inner.get("name", "") if isinstance(inner, dict) else ""
                if name:
                    names.append(name)
        if names:
            return " / ".join(names)

    # Fall back to cards with Commander partition
    cmd_cards = [c["name"] for c in cards if c["partition"] == "Commander"]
    if cmd_cards:
        return " / ".join(cmd_cards)

    return detail.get("name", "Unknown")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape Commander/EDH decklists from Moxfield and Archidekt"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--limit", type=int, default=10000, help="Max total decks")
    parser.add_argument(
        "--source",
        choices=["moxfield", "archidekt", "both"],
        default="both",
        help="Which API(s) to scrape",
    )
    parser.add_argument(
        "--min-cards", type=int, default=60,
        help="Skip decks with fewer cards (Commander = 100, but allow some slack)",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    all_decks: list[dict] = []

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        # Moxfield
        if args.source in ("moxfield", "both"):
            mox_limit = args.limit if args.source == "moxfield" else args.limit // 2
            moxfield_decks = scrape_moxfield(client, mox_limit, args.min_cards)
            all_decks.extend(moxfield_decks)

        # Archidekt
        if args.source in ("archidekt", "both"):
            arch_limit = args.limit - len(all_decks) if args.source == "both" else args.limit
            archidekt_decks = scrape_archidekt(client, arch_limit, args.min_cards)
            all_decks.extend(archidekt_decks)

    if not all_decks:
        print("No decks collected. Check network access and API availability.")
        return 1

    # Deduplicate by card list fingerprint
    seen: set[str] = set()
    unique: list[dict] = []
    for deck in all_decks:
        fp = _deck_fingerprint(deck["cards"])
        if fp not in seen:
            seen.add(fp)
            unique.append(deck)

    dupes = len(all_decks) - len(unique)
    print(f"\nTotal: {len(all_decks)} collected -> {len(unique)} unique ({dupes} duplicates removed)")

    # Summary by source
    by_source: dict[str, int] = {}
    for d in unique:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}")

    # Write output
    with open(args.output, "w") as f:
        for deck in unique:
            f.write(json.dumps(deck) + "\n")

    print(f"\nWritten to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
