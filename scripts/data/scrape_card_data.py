#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""
Scrape rich card data from public TCG APIs.

Supported games:
  - magic   (Scryfall)
  - yugioh  (YGOProDeck)
  - pokemon (Pokemon TCG API)

Data types:
  - rulings  — card rulings / errata text
  - prices   — market prices (USD/EUR)
  - images   — card art downloads
  - meta     — tournament / meta / staple data
  - sets     — set / collection info with release dates

Usage:
    uv run scripts/data/scrape_card_data.py --game magic --data-type prices
    uv run scripts/data/scrape_card_data.py --game yugioh --data-type sets --dry-run
    uv run scripts/data/scrape_card_data.py --game all --data-type rulings --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "DeckSage/1.0 (research project)"
RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"

# Rate-limit delays (seconds).  Scryfall asks for 100ms between requests;
# image downloads use a politer 50ms.  YGOProDeck and pokemontcg.io have
# no documented hard limits but we stay conservative.
DELAY_SCRYFALL = 0.10
DELAY_SCRYFALL_IMAGE = 0.05
DELAY_YGOPRODECK = 1.0
DELAY_POKEMON = 1.0
DELAY_EDHREC = 1.0

MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # exponential backoff multiplier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(name: str) -> str:
    """Turn a card name into a safe filesystem string."""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name[:120]  # cap length


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_retries: int = MAX_RETRIES,
) -> httpx.Response:
    """Issue an HTTP request with exponential-backoff retry on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = await client.request(method, url, params=params)
            # Retry on 429 / 5xx
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = BACKOFF_BASE ** (attempt + 1)
                print(
                    f"  [retry] {resp.status_code} on {url} — "
                    f"waiting {wait:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait)
                continue
            return resp
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            wait = BACKOFF_BASE ** (attempt + 1)
            print(
                f"  [retry] {type(exc).__name__} on {url} — "
                f"waiting {wait:.1f}s (attempt {attempt + 1}/{max_retries})"
            )
            await asyncio.sleep(wait)

    # Exhausted retries — raise last error or a generic one
    if last_exc is not None:
        raise last_exc
    raise httpx.RequestError(f"Failed after {max_retries} retries: {url}")


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET + parse JSON, with retry."""
    resp = await _request_with_retry(client, "GET", url, params=params)
    resp.raise_for_status()
    return resp.json()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"  Saved to {path}")


def _progress(label: str, i: int, total: int | None = None, every: int = 100) -> None:
    if i > 0 and i % every == 0:
        suffix = f"/{total}" if total else ""
        print(f"  [{label}] {i}{suffix} items processed")


# ---------------------------------------------------------------------------
# Scryfall bulk-data helper
# ---------------------------------------------------------------------------


async def _scryfall_bulk_oracle_cards(
    client: httpx.AsyncClient,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Download the Scryfall oracle_cards bulk file and return card dicts."""
    print("  [scryfall] Fetching bulk-data manifest...")
    manifest = await _get_json(client, "https://api.scryfall.com/bulk-data")
    download_url: str | None = None
    for entry in manifest.get("data", []):
        if entry.get("type") == "oracle_cards":
            download_url = entry["download_uri"]
            break
    if download_url is None:
        raise RuntimeError("Could not find oracle_cards in Scryfall bulk-data manifest")

    print(f"  [scryfall] Downloading oracle_cards bulk file...")
    resp = await _request_with_retry(client, "GET", download_url)
    resp.raise_for_status()
    cards: list[dict[str, Any]] = resp.json()
    print(f"  [scryfall] Loaded {len(cards)} oracle cards")
    if limit is not None:
        cards = cards[:limit]
    return cards


# ===================================================================
# RULINGS
# ===================================================================


async def scrape_magic_rulings(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape Magic card rulings from Scryfall (per-card endpoint)."""
    print("[magic/rulings] Starting...")
    cards = await _scryfall_bulk_oracle_cards(client, limit=limit)

    if dry_run:
        print(f"  [dry-run] Would fetch rulings for {len(cards)} cards")
        return {"game": "magic", "data_type": "rulings", "dry_run": True, "card_count": len(cards)}

    rulings_out: list[dict[str, Any]] = []
    for i, card in enumerate(cards):
        _progress("magic/rulings", i, len(cards))
        card_id = card["id"]
        card_name = card.get("name", card_id)
        await asyncio.sleep(DELAY_SCRYFALL)
        try:
            data = await _get_json(
                client, f"https://api.scryfall.com/cards/{card_id}/rulings"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        entries = data.get("data", [])
        if entries:
            rulings_out.append(
                {
                    "id": card_id,
                    "name": card_name,
                    "rulings": [
                        {"date": r.get("published_at", ""), "text": r.get("comment", "")}
                        for r in entries
                    ],
                }
            )

    result = {
        "game": "magic",
        "data_type": "rulings",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "scryfall",
        "count": len(rulings_out),
        "cards": rulings_out,
    }
    print(f"[magic/rulings] Done. {len(rulings_out)} cards with rulings.")
    return result


async def scrape_yugioh_rulings(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape YGO card text (ruling-relevant info) from YGOProDeck."""
    print("[yugioh/rulings] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all YGO cards for ruling text")
        return {"game": "yugioh", "data_type": "rulings", "dry_run": True}

    await asyncio.sleep(DELAY_YGOPRODECK)
    data = await _get_json(
        client, "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    )
    cards = data.get("data", [])
    if limit is not None:
        cards = cards[:limit]

    rulings_out: list[dict[str, Any]] = []
    for i, card in enumerate(cards):
        _progress("yugioh/rulings", i, len(cards))
        rulings_out.append(
            {
                "id": card.get("id"),
                "name": card.get("name", ""),
                "type": card.get("type", ""),
                "desc": card.get("desc", ""),
                "archetype": card.get("archetype", ""),
                "misc_info": card.get("misc_info", []),
            }
        )

    result = {
        "game": "yugioh",
        "data_type": "rulings",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "count": len(rulings_out),
        "cards": rulings_out,
    }
    print(f"[yugioh/rulings] Done. {len(rulings_out)} cards.")
    return result


# ===================================================================
# PRICES
# ===================================================================


async def scrape_magic_prices(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Extract prices from Scryfall bulk oracle_cards data."""
    print("[magic/prices] Starting...")
    cards = await _scryfall_bulk_oracle_cards(client, limit=limit)

    if dry_run:
        print(f"  [dry-run] Would extract prices for {len(cards)} cards")
        return {"game": "magic", "data_type": "prices", "dry_run": True, "card_count": len(cards)}

    prices_out: list[dict[str, Any]] = []
    for i, card in enumerate(cards):
        _progress("magic/prices", i, len(cards))
        prices = card.get("prices")
        if prices and any(v is not None for v in prices.values()):
            prices_out.append(
                {
                    "id": card["id"],
                    "name": card.get("name", ""),
                    "set": card.get("set", ""),
                    "prices": prices,
                }
            )

    result = {
        "game": "magic",
        "data_type": "prices",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "scryfall",
        "count": len(prices_out),
        "cards": prices_out,
    }
    print(f"[magic/prices] Done. {len(prices_out)} cards with prices.")
    return result


async def scrape_yugioh_prices(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape YGO card prices from YGOProDeck."""
    print("[yugioh/prices] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all YGO cards for price data")
        return {"game": "yugioh", "data_type": "prices", "dry_run": True}

    await asyncio.sleep(DELAY_YGOPRODECK)
    data = await _get_json(
        client, "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    )
    cards = data.get("data", [])
    if limit is not None:
        cards = cards[:limit]

    prices_out: list[dict[str, Any]] = []
    for i, card in enumerate(cards):
        _progress("yugioh/prices", i, len(cards))
        card_prices = card.get("card_prices", [])
        if card_prices:
            prices_out.append(
                {
                    "id": card.get("id"),
                    "name": card.get("name", ""),
                    "card_prices": card_prices,
                }
            )

    result = {
        "game": "yugioh",
        "data_type": "prices",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "count": len(prices_out),
        "cards": prices_out,
    }
    print(f"[yugioh/prices] Done. {len(prices_out)} cards with prices.")
    return result


async def scrape_pokemon_prices(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape Pokemon card prices from pokemontcg.io."""
    print("[pokemon/prices] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all Pokemon cards for price data")
        return {"game": "pokemon", "data_type": "prices", "dry_run": True}

    prices_out: list[dict[str, Any]] = []
    page = 1
    page_size = 250
    fetched = 0

    while True:
        await asyncio.sleep(DELAY_POKEMON)
        data = await _get_json(
            client,
            "https://api.pokemontcg.io/v2/cards",
            params={
                "pageSize": page_size,
                "page": page,
                "select": "id,name,set,tcgplayer",
            },
        )
        cards = data.get("data", [])
        if not cards:
            break

        for card in cards:
            tcgplayer = card.get("tcgplayer")
            if tcgplayer and tcgplayer.get("prices"):
                prices_out.append(
                    {
                        "id": card.get("id", ""),
                        "name": card.get("name", ""),
                        "set": card.get("set", {}).get("name", ""),
                        "tcgplayer": tcgplayer,
                    }
                )
            fetched += 1
            if limit is not None and fetched >= limit:
                break

        _progress("pokemon/prices", fetched, data.get("totalCount"))

        if limit is not None and fetched >= limit:
            break
        total_count = data.get("totalCount", 0)
        if page * page_size >= total_count:
            break
        page += 1

    result = {
        "game": "pokemon",
        "data_type": "prices",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pokemontcg.io",
        "count": len(prices_out),
        "cards": prices_out,
    }
    print(f"[pokemon/prices] Done. {len(prices_out)} cards with prices.")
    return result


# ===================================================================
# IMAGES
# ===================================================================


async def _download_image(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    delay: float,
) -> bool:
    """Download a single image if it does not already exist. Returns True if downloaded."""
    if dest.exists():
        return False
    await asyncio.sleep(delay)
    resp = await _request_with_retry(client, "GET", url)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return True


async def scrape_magic_images(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Download Magic card images from Scryfall."""
    print("[magic/images] Starting...")
    cards = await _scryfall_bulk_oracle_cards(client, limit=limit)
    image_dir = RAW_DIR / "images" / "magic"
    image_dir.mkdir(parents=True, exist_ok=True)

    downloadable = []
    for card in cards:
        image_uris = card.get("image_uris", {})
        img_url = image_uris.get("normal")
        if not img_url:
            continue
        name = _sanitize_filename(card.get("name", card["id"]))
        dest = image_dir / f"{name}.jpg"
        downloadable.append((card.get("name", ""), img_url, dest))

    if dry_run:
        existing = sum(1 for _, _, d in downloadable if d.exists())
        print(
            f"  [dry-run] {len(downloadable)} cards with images, "
            f"{existing} already downloaded, {len(downloadable) - existing} to fetch"
        )
        return {
            "game": "magic",
            "data_type": "images",
            "dry_run": True,
            "total": len(downloadable),
            "existing": existing,
        }

    downloaded = 0
    skipped = 0
    for i, (card_name, url, dest) in enumerate(downloadable):
        _progress("magic/images", i, len(downloadable))
        try:
            if await _download_image(client, url, dest, delay=DELAY_SCRYFALL_IMAGE):
                downloaded += 1
            else:
                skipped += 1
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  [warn] Failed to download image for {card_name}: {exc}")

    result = {
        "game": "magic",
        "data_type": "images",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "scryfall",
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "directory": str(image_dir),
    }
    print(f"[magic/images] Done. {downloaded} downloaded, {skipped} skipped (existing).")
    return result


async def scrape_yugioh_images(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Download YGO card images from YGOProDeck."""
    print("[yugioh/images] Starting...")
    await asyncio.sleep(DELAY_YGOPRODECK)
    data = await _get_json(
        client, "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    )
    cards = data.get("data", [])
    if limit is not None:
        cards = cards[:limit]

    image_dir = RAW_DIR / "images" / "yugioh"
    image_dir.mkdir(parents=True, exist_ok=True)

    downloadable = []
    for card in cards:
        imgs = card.get("card_images", [])
        if not imgs:
            continue
        img_url = imgs[0].get("image_url")
        if not img_url:
            continue
        name = _sanitize_filename(card.get("name", str(card.get("id", ""))))
        dest = image_dir / f"{name}.jpg"
        downloadable.append((card.get("name", ""), img_url, dest))

    if dry_run:
        existing = sum(1 for _, _, d in downloadable if d.exists())
        print(
            f"  [dry-run] {len(downloadable)} cards with images, "
            f"{existing} already downloaded, {len(downloadable) - existing} to fetch"
        )
        return {
            "game": "yugioh",
            "data_type": "images",
            "dry_run": True,
            "total": len(downloadable),
            "existing": existing,
        }

    downloaded = 0
    skipped = 0
    for i, (card_name, url, dest) in enumerate(downloadable):
        _progress("yugioh/images", i, len(downloadable))
        try:
            if await _download_image(client, url, dest, delay=DELAY_SCRYFALL_IMAGE):
                downloaded += 1
            else:
                skipped += 1
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  [warn] Failed to download image for {card_name}: {exc}")

    result = {
        "game": "yugioh",
        "data_type": "images",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "directory": str(image_dir),
    }
    print(f"[yugioh/images] Done. {downloaded} downloaded, {skipped} skipped (existing).")
    return result


async def scrape_pokemon_images(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Download Pokemon card images from pokemontcg.io."""
    print("[pokemon/images] Starting...")
    image_dir = RAW_DIR / "images" / "pokemon"
    image_dir.mkdir(parents=True, exist_ok=True)

    # First collect all card image URLs via paginated API
    downloadable: list[tuple[str, str, Path]] = []
    page = 1
    page_size = 250
    fetched = 0

    while True:
        await asyncio.sleep(DELAY_POKEMON)
        data = await _get_json(
            client,
            "https://api.pokemontcg.io/v2/cards",
            params={
                "pageSize": page_size,
                "page": page,
                "select": "id,name,images",
            },
        )
        cards = data.get("data", [])
        if not cards:
            break

        for card in cards:
            images = card.get("images", {})
            img_url = images.get("large") or images.get("small")
            if not img_url:
                continue
            name = _sanitize_filename(card.get("name", card.get("id", "")))
            card_id = card.get("id", "").replace("/", "_")
            # Use card ID in filename to avoid collisions (many Pokemon share names)
            dest = image_dir / f"{name}_{card_id}.jpg"
            downloadable.append((card.get("name", ""), img_url, dest))
            fetched += 1
            if limit is not None and fetched >= limit:
                break

        _progress("pokemon/images-index", fetched, data.get("totalCount"))
        if limit is not None and fetched >= limit:
            break
        total_count = data.get("totalCount", 0)
        if page * page_size >= total_count:
            break
        page += 1

    if dry_run:
        existing = sum(1 for _, _, d in downloadable if d.exists())
        print(
            f"  [dry-run] {len(downloadable)} cards with images, "
            f"{existing} already downloaded, {len(downloadable) - existing} to fetch"
        )
        return {
            "game": "pokemon",
            "data_type": "images",
            "dry_run": True,
            "total": len(downloadable),
            "existing": existing,
        }

    downloaded = 0
    skipped = 0
    for i, (card_name, url, dest) in enumerate(downloadable):
        _progress("pokemon/images", i, len(downloadable))
        try:
            if await _download_image(client, url, dest, delay=DELAY_SCRYFALL_IMAGE):
                downloaded += 1
            else:
                skipped += 1
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  [warn] Failed to download image for {card_name}: {exc}")

    result = {
        "game": "pokemon",
        "data_type": "images",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pokemontcg.io",
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "directory": str(image_dir),
    }
    print(f"[pokemon/images] Done. {downloaded} downloaded, {skipped} skipped (existing).")
    return result


# ===================================================================
# META / TOURNAMENT DATA
# ===================================================================


async def scrape_magic_meta(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape Magic meta/commander data from EDHREC."""
    print("[magic/meta] Starting (EDHREC)...")
    if dry_run:
        print("  [dry-run] Would fetch EDHREC commanders list + top commander details")
        return {"game": "magic", "data_type": "meta", "dry_run": True}

    await asyncio.sleep(DELAY_EDHREC)
    commanders_data = await _get_json(
        client, "https://json.edhrec.com/pages/commanders.json"
    )

    # Extract top commanders
    container = commanders_data.get("container", {})
    json_dict = container.get("json_dict", {})
    card_lists = json_dict.get("cardlists", [])

    top_commanders: list[dict[str, Any]] = []
    for cardlist in card_lists:
        for entry in cardlist.get("cardviews", []):
            top_commanders.append(
                {
                    "name": entry.get("name", ""),
                    "sanitized": entry.get("sanitized", ""),
                    "num_decks": entry.get("num_decks", 0),
                    "label": entry.get("label", ""),
                }
            )

    if limit is not None:
        top_commanders = top_commanders[:limit]

    # Fetch per-commander staple data for top N
    max_detail = min(len(top_commanders), limit or 20, 20)
    commander_details: list[dict[str, Any]] = []
    for i, cmdr in enumerate(top_commanders[:max_detail]):
        sanitized = cmdr.get("sanitized", "")
        if not sanitized:
            continue
        _progress("magic/meta-detail", i, max_detail, every=5)
        await asyncio.sleep(DELAY_EDHREC)
        try:
            detail = await _get_json(
                client,
                f"https://json.edhrec.com/pages/commanders/{sanitized}.json",
            )
            container_d = detail.get("container", {})
            json_d = container_d.get("json_dict", {})
            cardlists_d = json_d.get("cardlists", [])
            staples: list[str] = []
            for cl in cardlists_d:
                for cv in cl.get("cardviews", []):
                    staples.append(cv.get("name", ""))
            commander_details.append(
                {
                    "name": cmdr["name"],
                    "staple_count": len(staples),
                    "top_staples": staples[:30],
                }
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  [warn] Failed to fetch detail for {cmdr['name']}: {exc}")

    result = {
        "game": "magic",
        "data_type": "meta",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "edhrec",
        "top_commanders_count": len(top_commanders),
        "top_commanders": top_commanders,
        "commander_details": commander_details,
    }
    print(f"[magic/meta] Done. {len(top_commanders)} commanders, {len(commander_details)} with details.")
    return result


async def scrape_yugioh_meta(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape YGO staple cards from YGOProDeck."""
    print("[yugioh/meta] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch YGO staple cards")
        return {"game": "yugioh", "data_type": "meta", "dry_run": True}

    await asyncio.sleep(DELAY_YGOPRODECK)
    data = await _get_json(
        client,
        "https://db.ygoprodeck.com/api/v7/cardinfo.php",
        params={"staple": "yes"},
    )
    cards = data.get("data", [])
    if limit is not None:
        cards = cards[:limit]

    staples: list[dict[str, Any]] = []
    for card in cards:
        staples.append(
            {
                "id": card.get("id"),
                "name": card.get("name", ""),
                "type": card.get("type", ""),
                "desc": card.get("desc", ""),
                "archetype": card.get("archetype", ""),
            }
        )

    result = {
        "game": "yugioh",
        "data_type": "meta",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "count": len(staples),
        "staple_cards": staples,
    }
    print(f"[yugioh/meta] Done. {len(staples)} staple cards.")
    return result


# ===================================================================
# SETS / COLLECTIONS
# ===================================================================


async def scrape_magic_sets(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape Magic set data from Scryfall."""
    print("[magic/sets] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all Magic sets from Scryfall")
        return {"game": "magic", "data_type": "sets", "dry_run": True}

    await asyncio.sleep(DELAY_SCRYFALL)
    data = await _get_json(client, "https://api.scryfall.com/sets")
    sets_list = data.get("data", [])
    if limit is not None:
        sets_list = sets_list[:limit]

    sets_out: list[dict[str, Any]] = []
    for s in sets_list:
        sets_out.append(
            {
                "code": s.get("code", ""),
                "name": s.get("name", ""),
                "set_type": s.get("set_type", ""),
                "released_at": s.get("released_at", ""),
                "card_count": s.get("card_count", 0),
                "digital": s.get("digital", False),
                "icon_svg_uri": s.get("icon_svg_uri", ""),
            }
        )

    result = {
        "game": "magic",
        "data_type": "sets",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "scryfall",
        "count": len(sets_out),
        "sets": sets_out,
    }
    print(f"[magic/sets] Done. {len(sets_out)} sets.")
    return result


async def scrape_yugioh_sets(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape YGO set data from YGOProDeck."""
    print("[yugioh/sets] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all YGO sets from YGOProDeck")
        return {"game": "yugioh", "data_type": "sets", "dry_run": True}

    await asyncio.sleep(DELAY_YGOPRODECK)
    data = await _get_json(
        client, "https://db.ygoprodeck.com/api/v7/cardsets.php"
    )
    # cardsets.php returns a list directly
    sets_list = data if isinstance(data, list) else data.get("data", [])
    if limit is not None:
        sets_list = sets_list[:limit]

    sets_out: list[dict[str, Any]] = []
    for s in sets_list:
        sets_out.append(
            {
                "set_name": s.get("set_name", ""),
                "set_code": s.get("set_code", ""),
                "num_of_cards": s.get("num_of_cards", 0),
                "tcg_date": s.get("tcg_date", ""),
                "ocg_date": s.get("ocg_date", ""),
            }
        )

    result = {
        "game": "yugioh",
        "data_type": "sets",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "count": len(sets_out),
        "sets": sets_out,
    }
    print(f"[yugioh/sets] Done. {len(sets_out)} sets.")
    return result


async def scrape_pokemon_sets(
    client: httpx.AsyncClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scrape Pokemon set data from pokemontcg.io."""
    print("[pokemon/sets] Starting...")
    if dry_run:
        print("  [dry-run] Would fetch all Pokemon sets from pokemontcg.io")
        return {"game": "pokemon", "data_type": "sets", "dry_run": True}

    await asyncio.sleep(DELAY_POKEMON)
    data = await _get_json(client, "https://api.pokemontcg.io/v2/sets")
    sets_list = data.get("data", [])
    if limit is not None:
        sets_list = sets_list[:limit]

    sets_out: list[dict[str, Any]] = []
    for s in sets_list:
        sets_out.append(
            {
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "series": s.get("series", ""),
                "total": s.get("total", 0),
                "releaseDate": s.get("releaseDate", ""),
                "legalities": s.get("legalities", {}),
                "ptcgoCode": s.get("ptcgoCode", ""),
            }
        )

    result = {
        "game": "pokemon",
        "data_type": "sets",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pokemontcg.io",
        "count": len(sets_out),
        "sets": sets_out,
    }
    print(f"[pokemon/sets] Done. {len(sets_out)} sets.")
    return result


# ===================================================================
# Dispatch table
# ===================================================================

# Maps (game, data_type) -> async scraper function.
# Each scraper accepts (client, *, dry_run, limit) and returns a dict.
SCRAPERS: dict[tuple[str, str], Any] = {
    # Rulings
    ("magic", "rulings"): scrape_magic_rulings,
    ("yugioh", "rulings"): scrape_yugioh_rulings,
    # Prices
    ("magic", "prices"): scrape_magic_prices,
    ("yugioh", "prices"): scrape_yugioh_prices,
    ("pokemon", "prices"): scrape_pokemon_prices,
    # Images
    ("magic", "images"): scrape_magic_images,
    ("yugioh", "images"): scrape_yugioh_images,
    ("pokemon", "images"): scrape_pokemon_images,
    # Meta
    ("magic", "meta"): scrape_magic_meta,
    ("yugioh", "meta"): scrape_yugioh_meta,
    # Sets
    ("magic", "sets"): scrape_magic_sets,
    ("yugioh", "sets"): scrape_yugioh_sets,
    ("pokemon", "sets"): scrape_pokemon_sets,
}

ALL_GAMES = ["magic", "yugioh", "pokemon"]
ALL_DATA_TYPES = ["rulings", "prices", "images", "meta", "sets"]


def _output_path(game: str, data_type: str) -> Path:
    """Determine the output file path (images use directory instead)."""
    if data_type == "images":
        return RAW_DIR / "images" / game  # directory
    return RAW_DIR / f"{game}_{data_type}.json"


async def run_scraper(
    game: str,
    data_type: str,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    key = (game, data_type)
    scraper = SCRAPERS.get(key)
    if scraper is None:
        print(f"[skip] No scraper for {game}/{data_type}")
        return

    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(
        headers=headers, timeout=120.0, follow_redirects=True
    ) as client:
        try:
            result = await scraper(client, dry_run=dry_run, limit=limit)
        except httpx.HTTPStatusError as exc:
            print(
                f"[{game}/{data_type}] HTTP error: {exc.response.status_code} "
                f"{exc.response.text[:200]}",
                file=sys.stderr,
            )
            return
        except httpx.RequestError as exc:
            print(f"[{game}/{data_type}] Request error: {exc}", file=sys.stderr)
            return

    if dry_run:
        print(f"[{game}/{data_type}] Dry-run result: {json.dumps(result, indent=2)}")
        return

    # Images scraper manages its own output directory; others write JSON.
    if data_type != "images":
        out_path = _output_path(game, data_type)
        _write_json(out_path, result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape rich card data from public TCG APIs."
    )
    parser.add_argument(
        "--game",
        choices=ALL_GAMES + ["all"],
        default="all",
        help="Which game(s) to scrape (default: all)",
    )
    parser.add_argument(
        "--data-type",
        choices=ALL_DATA_TYPES + ["all"],
        default="all",
        help="Which data type(s) to scrape (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without making network requests (beyond initial metadata)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of items to process (useful for testing)",
    )
    args = parser.parse_args()

    games = ALL_GAMES if args.game == "all" else [args.game]
    data_types = ALL_DATA_TYPES if args.data_type == "all" else [args.data_type]

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"DeckSage card data scraper")
    print(f"  Games:      {', '.join(games)}")
    print(f"  Data types: {', '.join(data_types)}")
    print(f"  Dry run:    {args.dry_run}")
    print(f"  Limit:      {args.limit or 'none'}")
    print(f"  Output dir: {RAW_DIR}")
    print()

    for game in games:
        for data_type in data_types:
            asyncio.run(
                run_scraper(
                    game,
                    data_type,
                    dry_run=args.dry_run,
                    limit=args.limit,
                )
            )
            print()

    print("All done.")


if __name__ == "__main__":
    main()
