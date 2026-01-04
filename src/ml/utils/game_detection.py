"""
Centralized game detection utilities.

Unified game detection with fallback chain:
1. Explicit game field in deck metadata
2. File path analysis
3. Source/URL analysis
4. Collection type analysis
5. Card name heuristics (last resort)
"""

from pathlib import Path
from typing import Any

from .game_names import normalize_game_name


def detect_game_from_path(file_path: str | Path) -> str | None:
    """
    Detect game from file path.

    Args:
        file_path: Path to file or directory

    Returns:
        Game name in lowercase format, or None if cannot detect
    """
    path_str = str(file_path).lower()

    if "/yugioh/" in path_str or "/ygo/" in path_str:
        return "yugioh"
    if "/pokemon/" in path_str or "/pkm/" in path_str:
        return "pokemon"
    if "/magic/" in path_str or "/mtg/" in path_str:
        return "magic"
    if "/digimon/" in path_str or "/dig/" in path_str:
        return "digimon"
    if "/onepiece/" in path_str or "/opcg/" in path_str or "/opc/" in path_str:
        return "onepiece"
    if "/riftbound/" in path_str or "/rift/" in path_str or "/rft/" in path_str:
        return "riftbound"

    return None


def detect_game_from_source(source: str) -> str | None:
    """
    Detect game from source name.

    Args:
        source: Source name (e.g., "mtgtop8", "limitless-web", "ygoprodeck-tournament")

    Returns:
        Game name in lowercase format, or None if cannot detect
    """
    if not source:
        return None

    source_lower = source.lower()

    # Yu-Gi-Oh sources
    if "yugioh" in source_lower or "ygoprodeck" in source_lower or "ygo" in source_lower:
        return "yugioh"

    # Pokemon sources
    if "pokemon" in source_lower or "pkm" in source_lower:
        return "pokemon"

    # Digimon sources (limitless supports multiple games, check game parameter)
    if "digimon" in source_lower or "dig" in source_lower:
        return "digimon"

    # One Piece sources
    if "onepiece" in source_lower or "opcg" in source_lower or "opc" in source_lower:
        return "onepiece"

    # Riftbound sources
    if "riftbound" in source_lower or "rift" in source_lower or "riftdecks" in source_lower:
        return "riftbound"

    # Limitless TCG supports multiple games - need game parameter to distinguish
    # For now, default to pokemon if just "limitless" (backward compatibility)
    if "limitless" in source_lower:
        # Could be pokemon, digimon, or onepiece - need additional context
        # Default to pokemon for backward compatibility
        return "pokemon"

    # MTG sources (default for most sources)
    if any(x in source_lower for x in ["mtg", "scryfall", "deckbox", "mtgtop8", "goldfish"]):
        return "magic"

    return None


def detect_game_from_collection_type(collection_type: str) -> str | None:
    """
    Detect game from collection type string.

    Args:
        collection_type: Collection type (e.g., "YGODeck", "PokemonDeck", "Deck")

    Returns:
        Game name in lowercase format, or None if cannot detect
    """
    if not collection_type:
        return None

    type_lower = collection_type.lower()

    if "ygo" in type_lower:
        return "yugioh"
    if "pokemon" in type_lower:
        return "pokemon"
    if "digimon" in type_lower or "dig" in type_lower:
        return "digimon"
    if "onepiece" in type_lower or "opc" in type_lower:
        return "onepiece"
    if "riftbound" in type_lower or "rift" in type_lower:
        return "riftbound"
    # "Deck", "Set", "Cube" are ambiguous - need additional context
    # Return None to trigger fallback

    return None


def detect_game_from_card_name(card_name: str) -> str | None:
    """
    Detect game from card name patterns (heuristic, last resort).

    Args:
        card_name: Card name

    Returns:
        Game name in lowercase format, or None if cannot detect
    """
    if not card_name:
        return None

    name_lower = card_name.lower()

    # Pokemon patterns
    if any(x in name_lower for x in ["-ex", "-gx", "-v", "-vmax", "-vstar"]):
        return "pokemon"

    # Yu-Gi-Oh patterns
    if any(x in name_lower for x in ["blue-eyes", "dark magician", "exodia", "pot of greed"]):
        return "yugioh"

    # Digimon patterns
    if any(x in name_lower for x in ["agumon", "gabumon", "digivolve", "digimon", "lv.", "lv "]):
        return "digimon"

    # One Piece patterns
    if any(
        x in name_lower for x in ["luffy", "zoro", "nami", "sanji", "don!!", "leader", "one piece"]
    ):
        return "onepiece"

    # Riftbound patterns
    if any(
        x in name_lower
        for x in [
            "champion",
            "domain",
            "body",
            "calm",
            "chaos",
            "fury",
            "mind",
            "order",
            "riftbound",
        ]
    ):
        return "riftbound"

    # MTG patterns (too many to list, default fallback)
    # Return None to use default

    return None


def detect_game(
    deck: dict[str, Any] | None = None,
    file_path: str | Path | None = None,
    source: str | None = None,
    collection_type: str | None = None,
    default: str = "magic",
) -> str:
    """
    Unified game detection with fallback chain.

    Detection order:
    1. Explicit game field in deck metadata
    2. File path analysis
    3. Source/URL analysis
    4. Collection type analysis
    5. Card name heuristics (if deck provided)
    6. Default fallback

    Args:
        deck: Deck dictionary (optional)
        file_path: Path to file (optional)
        source: Source name (optional)
        collection_type: Collection type string (optional)
        default: Default game if cannot detect (default: "magic")

    Returns:
        Game name in lowercase format
    """
    # 1. Check explicit game field
    if deck and "game" in deck:
        game = deck["game"]
        if game:
            return normalize_game_name(game, "lowercase")

    # 2. File path analysis
    if file_path:
        game = detect_game_from_path(file_path)
        if game:
            return game

    # 3. Source/URL analysis
    if deck and "source" in deck:
        source = deck["source"]
    if source:
        game = detect_game_from_source(source)
        if game:
            return game

    # Check URL if available
    if deck and "url" in deck:
        url = deck["url"]
        if url:
            game = detect_game_from_source(url)
            if game:
                return game

    # 4. Collection type analysis
    if collection_type:
        game = detect_game_from_collection_type(collection_type)
        if game:
            return game

    if deck and "type" in deck:
        type_obj = deck["type"]
        if isinstance(type_obj, dict) and "type" in type_obj:
            game = detect_game_from_collection_type(type_obj["type"])
            if game:
                return game

    # 5. Card name heuristics (last resort, only if deck provided)
    if deck and "cards" in deck:
        cards = deck["cards"]
        if cards and len(cards) > 0:
            # Check first few cards
            for card in cards[:5]:
                card_name = card.get("name", "") if isinstance(card, dict) else str(card)
                game = detect_game_from_card_name(card_name)
                if game:
                    return game

    # 6. Default fallback
    return default
