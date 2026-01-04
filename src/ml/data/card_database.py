#!/usr/bin/env python3
"""
Card Database: Lookup cards by name and determine which game they belong to.

Uses actual card databases from backend instead of heuristics.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from ml.data.card_name_normalizer import (
    find_best_match,
    normalize_for_comparison,
)


try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class CardDatabase:
    """Multi-game card database with lookup capabilities."""

    def __init__(self, data_dir: Path | None = None):
        """Initialize card database from backend data."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "backend" / "data-full"

        self.data_dir = data_dir
        self._magic_cards: set[str] = set()
        self._pokemon_cards: set[str] = set()
        self._yugioh_cards: set[str] = set()
        self._digimon_cards: set[str] = set()
        self._onepiece_cards: set[str] = set()
        self._riftbound_cards: set[str] = set()
        self._loaded = False
        # Cached lowercase sets for performance
        self._magic_lower: set[str] | None = None
        self._pokemon_lower: set[str] | None = None
        self._yugioh_lower: set[str] | None = None
        self._digimon_lower: set[str] | None = None
        self._onepiece_lower: set[str] | None = None
        self._riftbound_lower: set[str] | None = None

    def _load_magic_cards(self) -> set[str]:
        """Load Magic card names from Scryfall data."""
        cards: set[str] = set()
        # Try multiple possible paths
        possible_paths = [
            self.data_dir / "games" / "magic" / "scryfall" / "cards",
            self.data_dir / "magic" / "scryfall" / "cards",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "magic"
            / "scryfall"
            / "cards",
        ]

        scryfall_dir = None
        for path in possible_paths:
            if path.exists():
                scryfall_dir = path
                break

        if not scryfall_dir:
            logger.warning(f"Scryfall directory not found in any of: {possible_paths}")
            return cards

        # Try JSON files first (uncompressed)
        json_files = list(scryfall_dir.glob("*.json"))
        if json_files:
            logger.debug(f"Loading from {len(json_files)} JSON files...")
            for json_file in json_files[:5000]:  # Load more for better coverage
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                        # Handle both single card and card array
                        if isinstance(data, list):
                            for card in data:
                                if isinstance(card, dict) and "name" in card:
                                    cards.add(card["name"])
                        elif isinstance(data, dict):
                            if "name" in data:
                                cards.add(data["name"])
                            # Also check for "data" array (API response format)
                            if "data" in data and isinstance(data["data"], list):
                                for card in data["data"]:
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                except Exception:
                    continue

        # Try zst files (compressed) - these are the actual data files
        zst_files = list(scryfall_dir.glob("*.json.zst"))
        if zst_files:
            logger.debug(f"Loading from {len(zst_files)} zst files...")
            # Load more zst files to get better coverage
            # Prioritize common cards first (alphabetically earlier files often have common cards)
            sorted_zst = sorted(zst_files)
            for zst_file in sorted_zst[:5000]:  # Load more for better coverage
                try:
                    result = subprocess.run(
                        ["zstd", "-d", "-c", str(zst_file)],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        # Handle both single card and card array
                        if isinstance(data, list):
                            for card in data:
                                if isinstance(card, dict) and "name" in card:
                                    cards.add(card["name"])
                        elif isinstance(data, dict):
                            if "name" in data:
                                cards.add(data["name"])
                            if "data" in data and isinstance(data["data"], list):
                                for card in data["data"]:
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                except Exception:
                    continue

        logger.info(f"Loaded {len(cards)} Magic cards")
        return cards

    def _load_pokemon_cards(self) -> set[str]:
        """Load Pokémon card names from backend data."""
        cards: set[str] = set()

        # Try multiple possible paths
        possible_paths = [
            self.data_dir / "games" / "pokemon" / "pokemontcg-data",
            self.data_dir / "pokemon" / "pokemontcg-data",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "pokemon"
            / "pokemontcg-data",
        ]

        pokemon_dir = None
        for path in possible_paths:
            if path.exists():
                pokemon_dir = path
                break

        if pokemon_dir:
            for json_file in list(pokemon_dir.glob("**/*.json"))[:500]:
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "name" in data:
                            cards.add(data["name"])
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and "name" in item:
                                    cards.add(item["name"])
                except Exception:
                    continue

        # Try limitless-web (decks with card names)
        limitless_paths = [
            self.data_dir / "games" / "pokemon" / "limitless-web",
            self.data_dir / "pokemon" / "limitless-web",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "pokemon"
            / "limitless-web",
        ]

        for limitless_dir in limitless_paths:
            if limitless_dir.exists():
                zst_files = list(limitless_dir.glob("*.json.zst"))
                logger.debug(f"Loading from {len(zst_files)} limitless zst files...")
                for zst_file in zst_files[:1000]:  # Increased limit
                    try:
                        result = subprocess.run(
                            ["zstd", "-d", "-c", str(zst_file)],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            # Extract card names from partitions
                            for part in data.get("partitions", []):
                                for card in part.get("cards", []):
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                    except Exception:
                        continue
                break  # Only process first matching directory

        logger.info(f"Loaded {len(cards)} Pokémon cards")
        return cards

    def _load_yugioh_cards(self) -> set[str]:
        """Load Yu-Gi-Oh! card names from ygoprodeck data."""
        cards: set[str] = set()
        # Try multiple possible paths (note: some have double "games/games" nesting)
        possible_paths = [
            self.data_dir / "games" / "yugioh" / "ygoprodeck" / "cards",
            self.data_dir / "games" / "games" / "yugioh" / "ygoprodeck" / "cards",
            self.data_dir / "yugioh" / "ygoprodeck" / "cards",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "games"
            / "yugioh"
            / "ygoprodeck"
            / "cards",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "yugioh"
            / "ygoprodeck"
            / "cards",
        ]

        ygo_dir = None
        for path in possible_paths:
            if path.exists():
                ygo_dir = path
                break

        if not ygo_dir:
            logger.warning(f"Yu-Gi-Oh! directory not found in any of: {possible_paths}")
            return cards

        # Try JSON files
        json_files = list(ygo_dir.glob("*.json"))
        if json_files:
            for json_file in json_files[:1000]:
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                        if "name" in data:
                            cards.add(data["name"])
                except Exception:
                    continue

        # Try zst files
        zst_files = list(ygo_dir.glob("*.json.zst"))
        if zst_files:
            logger.debug(f"Loading from {len(zst_files)} Yu-Gi-Oh! zst files...")
            for zst_file in zst_files[:2000]:  # Increased limit
                try:
                    result = subprocess.run(
                        ["zstd", "-d", "-c", str(zst_file)],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if "name" in data:
                            cards.add(data["name"])
                except Exception:
                    continue

        logger.info(f"Loaded {len(cards)} Yu-Gi-Oh! cards")
        return cards

    def _load_digimon_cards(self) -> set[str]:
        """Load Digimon card names from backend data."""
        cards: set[str] = set()

        # Try multiple possible paths
        possible_paths = [
            self.data_dir / "games" / "digimon" / "limitless",
            self.data_dir / "digimon" / "limitless",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "digimon"
            / "limitless",
        ]

        for digimon_dir in possible_paths:
            if digimon_dir.exists():
                # Load from deck collections (extract card names)
                json_files = list(digimon_dir.glob("*.json"))
                for json_file in json_files[:1000]:
                    try:
                        with open(json_file) as f:
                            data = json.load(f)
                            # Extract card names from partitions
                            for part in data.get("partitions", []):
                                for card in part.get("cards", []):
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                    except Exception:
                        continue
                break

        logger.info(f"Loaded {len(cards)} Digimon cards")
        return cards

    def _load_onepiece_cards(self) -> set[str]:
        """Load One Piece card names from backend data."""
        cards: set[str] = set()

        # Try multiple possible paths
        possible_paths = [
            self.data_dir / "games" / "onepiece" / "limitless",
            self.data_dir / "onepiece" / "limitless",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "onepiece"
            / "limitless",
        ]

        for onepiece_dir in possible_paths:
            if onepiece_dir.exists():
                # Load from deck collections (extract card names)
                json_files = list(onepiece_dir.glob("*.json"))
                for json_file in json_files[:1000]:
                    try:
                        with open(json_file) as f:
                            data = json.load(f)
                            # Extract card names from partitions
                            for part in data.get("partitions", []):
                                for card in part.get("cards", []):
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                    except Exception:
                        continue
                break

        logger.info(f"Loaded {len(cards)} One Piece cards")
        return cards

    def _load_riftbound_cards(self) -> set[str]:
        """Load Riftbound card names from backend data."""
        cards: set[str] = set()

        # Try multiple possible paths
        possible_paths = [
            self.data_dir / "games" / "riftbound" / "riftdecks",
            self.data_dir / "riftbound" / "riftdecks",
            Path(__file__).parent.parent.parent
            / "backend"
            / "data-full"
            / "games"
            / "riftbound"
            / "riftdecks",
        ]

        for riftbound_dir in possible_paths:
            if riftbound_dir.exists():
                # Load from deck collections (extract card names)
                json_files = list(riftbound_dir.glob("*.json"))
                for json_file in json_files[:1000]:
                    try:
                        with open(json_file) as f:
                            data = json.load(f)
                            # Extract card names from partitions
                            for part in data.get("partitions", []):
                                for card in part.get("cards", []):
                                    if isinstance(card, dict) and "name" in card:
                                        cards.add(card["name"])
                    except Exception:
                        continue
                break

        logger.info(f"Loaded {len(cards)} Riftbound cards")
        return cards

    def load(self) -> None:
        """Load all card databases."""
        if self._loaded:
            return

        self._magic_cards = self._load_magic_cards()
        self._pokemon_cards = self._load_pokemon_cards()
        self._yugioh_cards = self._load_yugioh_cards()
        self._digimon_cards = self._load_digimon_cards()
        self._onepiece_cards = self._load_onepiece_cards()
        self._riftbound_cards = self._load_riftbound_cards()

        # Pre-compute lowercase sets for performance
        self._magic_lower = {c.lower().strip() for c in self._magic_cards}
        self._pokemon_lower = {c.lower().strip() for c in self._pokemon_cards}
        self._yugioh_lower = {c.lower().strip() for c in self._yugioh_cards}
        self._digimon_lower = {c.lower().strip() for c in self._digimon_cards}
        self._onepiece_lower = {c.lower().strip() for c in self._onepiece_cards}
        self._riftbound_lower = {c.lower().strip() for c in self._riftbound_cards}

        self._loaded = True

    def get_game(self, card_name: str, fuzzy: bool = False) -> str | None:
        """
        Determine which game a card belongs to.

        Args:
            card_name: Card name to look up
            fuzzy: If True, try fuzzy matching if exact match fails

        Returns:
            Game name ("magic", "pokemon", "yugioh", "digimon", "onepiece", "riftbound") or None
        """
        self.load()

        card_norm = normalize_for_comparison(card_name)

        # Try exact match first (fast)
        if self._magic_lower and card_norm in self._magic_lower:
            return "magic"

        if self._pokemon_lower and card_norm in self._pokemon_lower:
            return "pokemon"

        if self._yugioh_lower and card_norm in self._yugioh_lower:
            return "yugioh"

        if self._digimon_lower and card_norm in self._digimon_lower:
            return "digimon"

        if self._onepiece_lower and card_norm in self._onepiece_lower:
            return "onepiece"

        if self._riftbound_lower and card_norm in self._riftbound_lower:
            return "riftbound"

        # Try fuzzy matching if enabled
        if fuzzy:
            # Try each game's card list
            for game_name, card_set in [
                ("magic", self._magic_cards),
                ("pokemon", self._pokemon_cards),
                ("yugioh", self._yugioh_cards),
                ("digimon", self._digimon_cards),
                ("onepiece", self._onepiece_cards),
                ("riftbound", self._riftbound_cards),
            ]:
                if card_set:
                    match, score = find_best_match(card_name, list(card_set), threshold=0.85)
                    if match:
                        logger.debug(
                            f"Fuzzy match: '{card_name}' -> '{match}' ({game_name}, score={score:.2f})"
                        )
                        return game_name

        return None

    def is_valid_card(self, card_name: str, game: str) -> bool:
        """Check if card name is valid for the specified game."""
        self.load()

        card_lower = card_name.strip().lower()

        # Use cached lowercase sets for performance
        if game == "magic":
            return self._magic_lower is not None and card_lower in self._magic_lower
        elif game == "pokemon":
            return self._pokemon_lower is not None and card_lower in self._pokemon_lower
        elif game == "yugioh":
            return self._yugioh_lower is not None and card_lower in self._yugioh_lower
        elif game == "digimon":
            return self._digimon_lower is not None and card_lower in self._digimon_lower
        elif game == "onepiece":
            return self._onepiece_lower is not None and card_lower in self._onepiece_lower
        elif game == "riftbound":
            return self._riftbound_lower is not None and card_lower in self._riftbound_lower

        return False

    def filter_cards_by_game(self, cards: list[str], game: str) -> tuple[list[str], list[str]]:
        """
        Filter cards to only include those from the specified game.

        Returns:
            (valid_cards, invalid_cards)
        """
        self.load()

        valid = []
        invalid = []

        for card in cards:
            card_game = self.get_game(card)
            if card_game == game:
                valid.append(card)
            else:
                invalid.append(card)

        return valid, invalid

    def get_card_data(self, card_name: str, game: str | None = None) -> dict[str, Any] | None:
        """
        Get full card data for a card (if available in database).

        Currently returns basic info. Can be extended to return full card data.
        """
        self.load()

        # If game not provided, detect it
        if not game:
            game = self.get_game(card_name)

        if not game:
            return None

        # For now, return basic info
        # In future, could load full card data from database files
        return {
            "name": card_name,
            "game": game,
            "is_valid": self.is_valid_card(card_name, game),
        }


# Global instance (lazy-loaded)
_global_db: CardDatabase | None = None


def get_card_database() -> CardDatabase:
    """Get global card database instance."""
    global _global_db
    if _global_db is None:
        _global_db = CardDatabase()
    return _global_db
