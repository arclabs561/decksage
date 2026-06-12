# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Expand Pokemon deck coverage by scraping Limitless TCG tournament pages.

Strategy:
1. Crawl /tournaments pages to discover tournament IDs
2. For each tournament, scrape the results page to find deck list IDs
3. For each new deck list ID, fetch /decks/list/{id} and parse the card list
4. Deduplicate against existing deck data
5. Write new decks to JSONL

Complements the Limitless API scraper by scraping the main limitlesstcg.com
website directly. The website has server-rendered HTML with card data in
<span class="card-count"> and <span class="card-name"> elements.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


BASE_URL = "https://limitlesstcg.com"
USER_AGENT = "DeckSage/1.0 (research project)"
RATE_LIMIT = 2.0  # seconds between requests
MAX_RETRIES = 3
BACKOFF_BASE = 3.0


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def fetch_page(client: httpx.Client, url: str) -> str | None:
    """GET with retry + rate limit. Returns HTML text or None on 404."""
    time.sleep(RATE_LIMIT)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, timeout=20)
            if resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                print(f"  [429] {url} -- waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            wait = BACKOFF_BASE ** (attempt + 1)
            print(f"  [{type(exc).__name__}] {url} -- waiting {wait:.0f}s")
            time.sleep(wait)
    return None


# ---------------------------------------------------------------------------
# Tournament discovery
# ---------------------------------------------------------------------------


def discover_tournament_ids(client: httpx.Client, max_pages: int = 21) -> list[dict]:
    """Scrape /tournaments pages to find tournament IDs."""
    tournaments: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/tournaments?page={page}"
        print(f"Fetching tournament page {page}/{max_pages}...")
        html = fetch_page(client, url)
        if not html:
            print(f"  No data on page {page}, stopping.")
            break

        for m in re.finditer(r"/tournaments/(\d+)", html):
            tid = m.group(1)
            if tid not in seen_ids:
                seen_ids.add(tid)
                tournaments.append({"id": tid})

    print(f"Discovered {len(tournaments)} tournaments.")
    return tournaments


# ---------------------------------------------------------------------------
# Deck list ID discovery from tournament pages
# ---------------------------------------------------------------------------


def discover_deck_ids_from_tournament(
    client: httpx.Client,
    tournament_id: str,
) -> list[dict]:
    """Scrape a tournament results page to find deck list IDs and metadata."""
    url = f"{BASE_URL}/tournaments/{tournament_id}"
    html = fetch_page(client, url)
    if not html:
        return []

    decks: list[dict] = []
    seen: set[str] = set()

    # Extract tournament name from <title>
    title_m = re.search(r"<title>([^<]+)</title>", html)
    tournament_name = ""
    if title_m:
        tournament_name = title_m.group(1).replace(" – Limitless", "").strip()

    # Extract date from og:description or content
    date_str = ""
    date_m = re.search(r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4})", html)
    if date_m:
        date_str = date_m.group(1)

    # Find /decks/list/{id} links
    for m in re.finditer(r"/decks/list/(\d+)", html):
        did = m.group(1)
        if did not in seen:
            seen.add(did)
            decks.append(
                {
                    "deck_id": did,
                    "tournament": tournament_name,
                    "tournament_id": tournament_id,
                    "date": date_str,
                }
            )

    return decks


# ---------------------------------------------------------------------------
# Deck list parsing -- regex-based, matches server-rendered HTML
# ---------------------------------------------------------------------------

# Pattern: <span class="card-count">N</span>\n<span class="card-name">Name</span>
_CARD_RE = re.compile(
    r'<span\s+class="card-count">(\d+)</span>\s*'
    r'<span\s+class="card-name">([^<]+)</span>',
    re.IGNORECASE,
)

# Section headers (Pokémon, Trainer, Energy) appear as headings
_SECTION_RE = re.compile(
    r'<(?:h[234]|div|span)[^>]*class="[^"]*decklist-type[^"]*"[^>]*>([^<]+)<',
    re.IGNORECASE,
)

# Archetype from title: "ArchetypeName by PlayerName – Limitless"
_TITLE_RE = re.compile(r"<title>(.+?)\s+by\s+(.+?)\s*[–-]\s*Limitless</title>")

# Event info from meta description: "Archetype decklist by Player - Nth Place Event - Date"
_META_DESC_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]+)"',
    re.IGNORECASE,
)
_PLACEMENT_RE = re.compile(r"(\d+)(?:st|nd|rd|th)\s+Place", re.IGNORECASE)
_EVENT_RE = re.compile(r"(?:Place|by\s+\S+(?:\s+\S+)*)\s*-\s*(.+?)(?:\s*-\s*\d)", re.IGNORECASE)


def parse_decklist_page(html: str) -> dict | None:
    """Parse a /decks/list/{id} page. Returns dict with cards + metadata or None."""
    cards = []
    current_partition = "Deck"

    # Extract cards using the span pattern
    # We need to track which section we're in. Sections appear before their cards.
    # Split HTML into chunks by card entries and look for section headers between them.
    pos = 0
    for m in _CARD_RE.finditer(html):
        # Check for section headers between previous position and this match
        chunk = html[pos : m.start()]
        for sm in _SECTION_RE.finditer(chunk):
            section = sm.group(1).strip().lower()
            if "pok" in section:
                current_partition = "Pokemon"
            elif "trainer" in section:
                current_partition = "Trainer"
            elif "energy" in section:
                current_partition = "Energy"

        count = int(m.group(1))
        name = m.group(2).strip()
        if name and 0 < count <= 60:
            cards.append({"name": name, "count": count, "partition": current_partition})
        pos = m.end()

    if not cards:
        return None

    # Extract metadata
    archetype = ""
    player = ""
    title_m = _TITLE_RE.search(html)
    if title_m:
        archetype = title_m.group(1).strip()
        player = title_m.group(2).strip()

    placement = 0
    event = ""
    meta_m = _META_DESC_RE.search(html)
    if meta_m:
        desc = meta_m.group(1)
        pl_m = _PLACEMENT_RE.search(desc)
        if pl_m:
            placement = int(pl_m.group(1))
        # Extract event name: "... - Nth Place EventName - Date"
        parts = desc.split(" - ")
        if len(parts) >= 3:
            event = parts[-2].strip()
        elif len(parts) == 2:
            event = parts[-1].strip()

    return {
        "archetype": archetype,
        "player": player,
        "event": event,
        "placement": placement,
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_existing_ids(paths: list[Path]) -> set[str]:
    """Load existing deck IDs to avoid re-scraping."""
    ids: set[str] = set()
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            did = str(d.get("deck_id", ""))
            ids.add(did)
            url = d.get("url", "")
            m = re.search(r"/decks/list/(\d+)", url)
            if m:
                ids.add(m.group(1))
    return ids


def _write_decks(path: Path, decks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for d in decks:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Expand Pokemon deck data from Limitless TCG website."
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL file")
    parser.add_argument(
        "--existing", type=Path, nargs="*", default=[], help="Existing JSONL files to dedup against"
    )
    parser.add_argument(
        "--max-tournament-pages", type=int, default=21, help="Max tournament listing pages"
    )
    parser.add_argument("--max-decks", type=int, default=15000, help="Max new decks to fetch")
    args = parser.parse_args()

    existing_ids = load_existing_ids(args.existing) if args.existing else set()
    print(f"Loaded {len(existing_ids)} existing deck IDs to skip.")

    now = datetime.now(UTC).isoformat()
    new_decks: list[dict] = []
    failed_ids = 0

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        # Phase 1: Discover tournaments
        tournaments = discover_tournament_ids(client, max_pages=args.max_tournament_pages)

        # Phase 2: Discover deck IDs from tournaments
        all_deck_metas: list[dict] = []
        seen_deck_ids: set[str] = set()
        print(f"\nDiscovering deck IDs from {len(tournaments)} tournaments...")
        for i, t in enumerate(tournaments):
            if len(all_deck_metas) >= args.max_decks:
                break
            if (i + 1) % 20 == 0:
                print(
                    f"  Progress: {i + 1}/{len(tournaments)} tournaments, {len(all_deck_metas)} deck IDs found"
                )
            decks = discover_deck_ids_from_tournament(client, t["id"])
            for d in decks:
                did = d["deck_id"]
                if did not in existing_ids and did not in seen_deck_ids:
                    seen_deck_ids.add(did)
                    all_deck_metas.append(d)

        print(f"Found {len(all_deck_metas)} new deck IDs from tournament pages.")

        # Phase 3: Fetch and parse each decklist
        to_fetch = min(len(all_deck_metas), args.max_decks)
        print(f"\nFetching {to_fetch} decklists...")
        for i, meta in enumerate(all_deck_metas[:to_fetch]):
            did = meta["deck_id"]
            html = fetch_page(client, f"{BASE_URL}/decks/list/{did}")
            if html is None:
                failed_ids += 1
                continue

            parsed = parse_decklist_page(html)
            if parsed is None:
                failed_ids += 1
                continue

            record = {
                "deck_id": did,
                "archetype": parsed["archetype"],
                "format": "",  # Will be enriched later
                "url": f"{BASE_URL}/decks/list/{did}",
                "source": "limitless-web",
                "player": parsed["player"],
                "event": parsed["event"] or meta.get("tournament", ""),
                "event_date": meta.get("date", ""),
                "placement": parsed["placement"],
                "created_at": meta.get("date", now),
                "scraped_at": now,
                "cards": parsed["cards"],
            }
            new_decks.append(record)

            if len(new_decks) % 100 == 0:
                print(
                    f"  Scraped {len(new_decks)} new decks (failed: {failed_ids}, remaining: {to_fetch - i - 1})"
                )
                _write_decks(args.output, new_decks)

    _write_decks(args.output, new_decks)

    print("\n--- Results ---")
    print(f"  New decks scraped: {len(new_decks)}")
    print(f"  Failed/404 IDs:   {failed_ids}")
    print(f"  Output:           {args.output}")


if __name__ == "__main__":
    main()
