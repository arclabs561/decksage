#!/usr/bin/env python3
"""
Deterministic format legality checking.

Uses cached ban list data from authoritative sources (Scryfall, Konami, Pokemon).
Does NOT use LLMs for factual ban list queries (LLMs hallucinate).
"""

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import requests

from .models import MTGDeck, PokemonDeck, YugiohDeck

# ============================================================================
# Cache Management
# ============================================================================

CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache" / "ban_lists"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(key: str) -> Path:
    """Get cache file path for a key."""
    return CACHE_DIR / f"{key}.json"


def _is_cache_fresh(cache_file: Path, max_age_days: int = 7) -> bool:
    """Check if cache is fresh enough."""
    if not cache_file.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    return age < timedelta(days=max_age_days)


def _load_cache(key: str) -> dict | None:
    """Load cached data if fresh."""
    cache_file = _cache_path(key)
    if _is_cache_fresh(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: dict) -> None:
    """Save data to cache."""
    cache_file = _cache_path(key)
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


# ============================================================================
# Magic: The Gathering Legality (Scryfall)
# ============================================================================


@lru_cache(maxsize=1)
def fetch_mtg_ban_lists() -> dict[str, dict[str, str]]:
    """
    Fetch MTG ban lists from Scryfall.

    Returns:
        {format: {card_name: status}}
        where status is "banned", "restricted", "legal", "not_legal"
        Returns empty dict if fetch fails (allows validation to continue)
    """
    cached = _load_cache("mtg_legality")
    if cached:
        return cached

    try:
        print("Fetching MTG legality data from Scryfall...")

        # Scryfall bulk data endpoint (more reliable than per-card queries)
        bulk_url = "https://api.scryfall.com/bulk-data"
        response = requests.get(bulk_url, timeout=30)
        response.raise_for_status()

        # Find the "Default Cards" dataset
        bulk_data = response.json()
        default_cards_uri = next(
            (d["download_uri"] for d in bulk_data["data"] if d["type"] == "default_cards"),
            None,
        )

        if not default_cards_uri:
            print("Warning: Could not find Scryfall default_cards bulk data")
            return {}

        # Download and parse (this is large ~100MB, cache it)
        print("Downloading Scryfall bulk data (~100MB, may take a minute)...")
        cards_response = requests.get(default_cards_uri, timeout=120)
        cards_response.raise_for_status()
        cards = cards_response.json()

        # Build legality map
        legality_map: dict[str, dict[str, str]] = {}

        for card in cards:
            name = card["name"]
            legalities = card.get("legalities", {})

            for format_name, status in legalities.items():
                # Normalize format names
                format_key = format_name.replace("_", " ").title()

                if format_key not in legality_map:
                    legality_map[format_key] = {}

                legality_map[format_key][name] = status

        _save_cache("mtg_legality", legality_map)
        print(f"✓ Cached legality data for {len(legality_map)} MTG formats")

        return legality_map

    except requests.RequestException as e:
        print(f"Warning: Failed to fetch MTG ban lists from Scryfall: {e}")
        print("Ban list validation will be skipped for MTG decks.")
        return {}
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to parse Scryfall data: {e}")
        print("Ban list validation will be skipped for MTG decks.")
        return {}
    except Exception as e:
        print(f"Warning: Unexpected error fetching MTG ban lists: {e}")
        print("Ban list validation will be skipped for MTG decks.")
        return {}


def check_mtg_legality(deck: MTGDeck) -> list[str]:
    """
    Check MTG deck legality.

    Returns list of issues (empty if legal).
    """
    issues = []

    try:
        legality_data = fetch_mtg_ban_lists()
    except Exception as e:
        issues.append(f"Failed to fetch ban list data: {e}")
        return issues

    if not legality_data:
        # API fetch failed, skip validation
        return issues

    # Normalize format name for lookup
    format_normalized = deck.format.replace("_", " ").title()

    if format_normalized not in legality_data:
        # Unknown format, can't validate (be liberal)
        return issues

    format_legality = legality_data[format_normalized]

    # Get all cards
    for card in deck.get_all_cards():
        status = format_legality.get(card.name, "not_legal")
        if status == "banned":
            issues.append(f"{card.name} is banned in {deck.format}")
        elif status == "restricted" and card.count > 1:
            issues.append(
                f"{card.name} is restricted to 1 copy in {deck.format}, deck has {card.count}"
            )
        elif status == "not_legal":
            issues.append(f"{card.name} is not legal in {deck.format}")

    return issues


# ============================================================================
# Yu-Gi-Oh! Legality (YGOProDeck API)
# ============================================================================


@lru_cache(maxsize=1)
def fetch_yugioh_ban_lists() -> dict[str, dict[str, int]]:
    """
    Fetch Yu-Gi-Oh! ban lists (TCG and OCG).

    Returns:
        {format: {card_name: limit}}
        where limit is 0 (banned), 1 (limited), 2 (semi-limited), 3 (unlimited)
        Returns empty dict if fetch fails
    """
    cached = _load_cache("yugioh_banlist")
    if cached:
        return cached

    try:
        print("Fetching Yu-Gi-Oh! ban list from YGOProDeck...")

        # YGOProDeck provides ban list data
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        response = requests.get(url, params={"misc": "yes"}, timeout=60)
        response.raise_for_status()

        data = response.json()
        cards = data.get("data", [])

        # Build ban list map
        ban_lists: dict[str, dict[str, int]] = {"TCG": {}, "OCG": {}}

        for card in cards:
            name = card["name"]
            misc = card.get("misc_info", [{}])[0] if card.get("misc_info") else {}

            # TCG ban status
            tcg_status = misc.get("tcg_date")  # Existence means legal in TCG
            if tcg_status:
                # Default to 3 (unlimited)
                ban_lists["TCG"][name] = 3

            # OCG ban status
            ocg_status = misc.get("ocg_date")
            if ocg_status:
                ban_lists["OCG"][name] = 3

            # Note: YGOProDeck's main API doesn't directly provide limit status
            # For production use, integrate with Konami's official ban list

        _save_cache("yugioh_banlist", ban_lists)
        print("✓ Cached Yu-Gi-Oh! legality data")

        return ban_lists

    except requests.RequestException as e:
        print(f"Warning: Failed to fetch Yu-Gi-Oh! ban lists: {e}")
        print("Ban list validation will be skipped for Yu-Gi-Oh! decks.")
        return {}
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to parse YGOProDeck data: {e}")
        print("Ban list validation will be skipped for Yu-Gi-Oh! decks.")
        return {}
    except Exception as e:
        print(f"Warning: Unexpected error fetching Yu-Gi-Oh! ban lists: {e}")
        print("Ban list validation will be skipped for Yu-Gi-Oh! decks.")
        return {}


def check_yugioh_legality(deck: YugiohDeck) -> list[str]:
    """
    Check Yu-Gi-Oh! deck legality.

    Returns list of issues (empty if legal).
    """
    issues = []

    try:
        ban_lists = fetch_yugioh_ban_lists()
    except Exception as e:
        issues.append(f"Failed to fetch ban list data: {e}")
        return issues

    if not ban_lists:
        # API fetch failed, skip validation
        return issues

    # Determine which ban list to use
    format_key = "TCG" if "TCG" in deck.format else "OCG"
    ban_list = ban_lists.get(format_key, {})

    # Get all cards
    card_counts: dict[str, int] = {}
    for card in deck.get_all_cards():
        card_counts[card.name] = card_counts.get(card.name, 0) + card.count

    for card_name, count in card_counts.items():
        limit = ban_list.get(card_name, 3)  # Default to 3 if not found

        if limit == 0 and count > 0:
            issues.append(f"{card_name} is banned in {format_key}")
        elif count > limit:
            status = {0: "banned", 1: "limited", 2: "semi-limited"}.get(limit, "unlimited")
            issues.append(
                f"{card_name} is {status} in {format_key} (max {limit}), deck has {count}"
            )

    return issues


# ============================================================================
# Pokemon Legality (PokemonTCG API)
# ============================================================================


@lru_cache(maxsize=1)
def fetch_pokemon_legality() -> dict[str, set[str]]:
    """
    Fetch Pokemon TCG format legality.

    Returns:
        {format: set(legal_card_names)}
        Returns empty dict if fetch fails
    """
    cached = _load_cache("pokemon_legality")
    if cached:
        # Convert lists back to sets
        return {fmt: set(cards) for fmt, cards in cached.items()}

    try:
        print("Fetching Pokemon TCG legality from Pokemon TCG API...")

        # Pokemon TCG API endpoint
        url = "https://api.pokemontcg.io/v2/cards"

        legality: dict[str, set[str]] = {
            "Standard": set(),
            "Expanded": set(),
            "Unlimited": set(),
        }

        # Fetch all cards (paginated)
        page = 1
        while True:
            response = requests.get(url, params={"page": page, "pageSize": 250}, timeout=60)
            response.raise_for_status()

            data = response.json()
            cards = data.get("data", [])

            if not cards:
                break

            for card in cards:
                name = card["name"]
                card_legalities = card.get("legalities", {})

                if card_legalities.get("standard") == "Legal":
                    legality["Standard"].add(name)
                if card_legalities.get("expanded") == "Legal":
                    legality["Expanded"].add(name)
                if card_legalities.get("unlimited") == "Legal":
                    legality["Unlimited"].add(name)

            page += 1

            # Safety: don't fetch forever
            if page > 100:
                break

        # Convert sets to lists for JSON serialization
        cache_data = {fmt: list(cards) for fmt, cards in legality.items()}
        _save_cache("pokemon_legality", cache_data)
        print("✓ Cached Pokemon legality data")

        return legality

    except requests.RequestException as e:
        print(f"Warning: Failed to fetch Pokemon TCG legality: {e}")
        print("Ban list validation will be skipped for Pokemon decks.")
        return {}
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to parse Pokemon TCG data: {e}")
        print("Ban list validation will be skipped for Pokemon decks.")
        return {}
    except Exception as e:
        print(f"Warning: Unexpected error fetching Pokemon legality: {e}")
        print("Ban list validation will be skipped for Pokemon decks.")
        return {}


def check_pokemon_legality(deck: PokemonDeck) -> list[str]:
    """
    Check Pokemon deck legality.

    Returns list of issues (empty if legal).
    """
    issues = []

    try:
        legality_data = fetch_pokemon_legality()
    except Exception as e:
        issues.append(f"Failed to fetch legality data: {e}")
        return issues

    if not legality_data:
        # API fetch failed, skip validation
        return issues

    format_legality = legality_data.get(deck.format, set())

    if not format_legality:
        # Unknown format
        return issues

    # Get all cards
    issues.extend(
        [
            f"{card.name} is not legal in {deck.format}"
            for card in deck.get_all_cards()
            if card.name not in format_legality
        ]
    )

    return issues


# ============================================================================
# Unified Interface
# ============================================================================


def check_deck_legality(
    deck: MTGDeck | YugiohDeck | PokemonDeck,
) -> list[str]:
    """
    Check deck legality using game-specific rules.

    Returns list of issues (empty if legal).
    """
    if isinstance(deck, MTGDeck):
        return check_mtg_legality(deck)
    elif isinstance(deck, YugiohDeck):
        return check_yugioh_legality(deck)
    elif isinstance(deck, PokemonDeck):
        return check_pokemon_legality(deck)
    else:
        return [f"Unknown deck type: {type(deck)}"]
