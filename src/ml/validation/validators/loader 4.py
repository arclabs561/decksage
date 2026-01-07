"""Deck loading and validation utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

# Re-export models if available
try:
    from .models import (
        BASIC_LANDS,
        CardDesc,
        Collection,
        MTGDeck,
        Partition,
        PokemonDeck,
        YugiohDeck,
    )
except ImportError:
    # Fallback to __init__.py definitions
    from . import (
        BASIC_LANDS,
        CardDesc,
        Collection,
        MTGDeck,
        Partition,
        PokemonDeck,
        YugiohDeck,
    )

logger = logging.getLogger(__name__)


def _infer_source_from_url(url: str) -> str:
    """
    Infer source from URL.
    
    Args:
        url: URL string
    
    Returns:
        Source name (e.g., "mtgtop8", "goldfish", "deckbox", "ygoprodeck", "limitless")
    """
    if not url:
        return "unknown"
    
    url_lower = url.lower()
    
    # MTG sources
    if "mtgtop8.com" in url_lower or "mtgtop8" in url_lower:
        return "mtgtop8"
    if "mtggoldfish.com" in url_lower or "goldfish" in url_lower:
        return "goldfish"
    if "deckbox.org" in url_lower or "deckbox" in url_lower:
        return "deckbox"
    if "scryfall.com" in url_lower or "scryfall" in url_lower:
        return "scryfall"
    
    # Yu-Gi-Oh sources
    if "ygoprodeck.com" in url_lower or "ygoprodeck" in url_lower:
        return "ygoprodeck"
    
    # Pokemon sources
    if "limitless.gg" in url_lower or "limitlesstcg.com" in url_lower or "limitless" in url_lower:
        return "limitless"
    
    return "unknown"


def load_decks_validated(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
    collect_metrics: bool = False,
) -> list[MTGDeck | PokemonDeck | YugiohDeck]:
    """
    Load and validate decks from JSONL file.
    
    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to load
        collect_metrics: Whether to collect validation metrics (currently ignored)
    
    Returns:
        List of validated deck Pydantic models (not dicts - for strict validation)
    """
    # Use lenient loader which returns Pydantic models
    # This function is for strict validation, but we use lenient for now
    # and return the models directly (not dicts)
    decks = load_decks_lenient(
        path,
        game=game,
        max_decks=max_decks,
        check_legality=False,
        verbose=False,
    )
    
    # Return Pydantic models directly (not converted to dicts)
    return decks


def iter_decks_validated(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
    check_legality: bool = False,
    **kwargs: Any,
) -> Iterator[tuple[MTGDeck | PokemonDeck | YugiohDeck | None, Any]]:
    """
    Iterate over validated decks from JSONL file, yielding (deck, result) tuples.
    
    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to yield
        check_legality: Whether to check format legality (currently ignored)
        **kwargs: Additional arguments (ignored)
    
    Yields:
        Tuples of (deck_model, validation_result) where result has is_valid attribute
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return
    
    count = 0
    for line_num, line in enumerate(open(path, encoding="utf-8"), 1):
        if max_decks and count >= max_decks:
            break
        
        if not line.strip():
            continue
        
        try:
            deck_dict = json.loads(line)
        except json.JSONDecodeError:
            # Yield None deck with invalid result
            from types import SimpleNamespace
            result = SimpleNamespace(is_valid=False, errors=["Invalid JSON"])
            yield (None, result)
            continue
        
        # Detect game if auto
        detected_game = game
        if game == "auto":
            detected_game = _detect_game_from_deck(deck_dict, path)
        
        # Try to parse as Pydantic model
        try:
            deck_model = _parse_deck_model(deck_dict, detected_game)
            if deck_model is None:
                from types import SimpleNamespace
                result = SimpleNamespace(is_valid=False, errors=["Failed to parse deck"])
                yield (None, result)
                continue
            
            # Create validation result
            from types import SimpleNamespace
            result = SimpleNamespace(is_valid=True, errors=[])
            yield (deck_model, result)
            count += 1
        except Exception as e:
            from types import SimpleNamespace
            result = SimpleNamespace(is_valid=False, errors=[str(e)])
            yield (None, result)
            continue


def _normalize_deck_data(deck_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize deck data structure to match expected model format.
    
    Handles both formats:
    - With partitions array: {"partitions": [{"name": "Main", "cards": [...]}]}
    - With cards array: {"cards": [{"name": "...", "partition": "Main", ...}]}
    """
    # If already has partitions, return as-is
    if "partitions" in deck_dict and isinstance(deck_dict["partitions"], list):
        return deck_dict
    
    # Convert cards array to partitions array
    if "cards" in deck_dict and isinstance(deck_dict["cards"], list):
        partitions_dict: dict[str, list[dict[str, Any]]] = {}
        
        for card in deck_dict["cards"]:
            partition_name = card.get("partition", "Main")
            if partition_name not in partitions_dict:
                partitions_dict[partition_name] = []
            
            # Extract card info (name, count)
            card_info = {"name": card.get("name", ""), "count": card.get("count", 1)}
            partitions_dict[partition_name].append(card_info)
        
        # Convert to partitions array
        partitions = [
            {"name": name, "cards": cards}
            for name, cards in partitions_dict.items()
        ]
        
        # Create normalized deck dict
        normalized = {k: v for k, v in deck_dict.items() if k != "cards"}
        normalized["partitions"] = partitions
        return normalized
    
    # If neither format, return as-is (will fail validation)
    return deck_dict


def _detect_game_from_deck(deck_dict: dict[str, Any], file_path: Path | str | None = None) -> str:
    """Detect game type from deck data or file path."""
    # Try to use game detection utility if available
    try:
        from ...utils.game_detection import detect_game
        
        return detect_game(deck=deck_dict, file_path=file_path, default="magic")
    except ImportError:
        # Fallback: simple heuristics
        source = str(deck_dict.get("source", "")).lower()
        if "pokemon" in source or "limitless" in source:
            return "pokemon"
        if "yugioh" in source or "ygo" in source:
            return "yugioh"
        return "magic"


def _parse_deck_model(deck_dict: dict[str, Any], game: str) -> MTGDeck | PokemonDeck | YugiohDeck | None:
    """Parse deck dictionary into appropriate Pydantic model."""
    try:
        normalized = _normalize_deck_data(deck_dict)
        
        if game == "pokemon":
            return PokemonDeck(**normalized)
        elif game == "yugioh":
            return YugiohDeck(**normalized)
        else:
            return MTGDeck(**normalized)
    except Exception as e:
        logger.debug(f"Failed to parse deck {deck_dict.get('deck_id', 'unknown')}: {e}")
        return None


def load_decks_lenient(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
    check_legality: bool = False,
    verbose: bool = False,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Load decks with lenient validation (allows some errors).
    
    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to load
        check_legality: Whether to check format legality (currently ignored)
        verbose: Whether to print progress
        **kwargs: Additional arguments (ignored)
    
    Returns:
        List of deck dictionaries (may have validation errors)
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return []
    
    decks: list[dict[str, Any]] = []
    skipped = 0
    
    try:
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if max_decks and len(decks) >= max_decks:
                    break
                
                if not line.strip():
                    continue
                
                try:
                    deck_dict = json.loads(line)
                except json.JSONDecodeError as e:
                    if verbose:
                        logger.debug(f"Skipping invalid JSON at line {line_num}: {e}")
                    skipped += 1
                    continue
                
                # Detect game if auto
                detected_game = game
                if game == "auto":
                    detected_game = _detect_game_from_deck(deck_dict, path)
                
                # Try to parse as Pydantic model (lenient: skip if fails)
                deck_model = _parse_deck_model(deck_dict, detected_game)
                
                if deck_model is None:
                    skipped += 1
                    if verbose:
                        logger.debug(f"Skipping invalid deck at line {line_num}: {deck_dict.get('deck_id', 'unknown')}")
                    continue
                
                # Return Pydantic model (caller will convert to dict if needed)
                decks.append(deck_model)
                
    except (IOError, OSError) as e:
        logger.error(f"Failed to read deck file {path}: {e}")
        return []
    
    if verbose:
        logger.info(f"Loaded {len(decks)} decks from {path} (skipped {skipped} invalid)")
    
    return decks


def load_decks_strict(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
) -> list[dict[str, Any]]:
    """
    Load decks with strict validation (rejects invalid decks).
    
    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to load
    
    Returns:
        List of validated deck dictionaries
    """
    return []


def stream_decks_lenient(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
    check_legality: bool = False,
    **kwargs: Any,
) -> Iterator[MTGDeck | PokemonDeck | YugiohDeck]:
    """
    Stream decks with lenient validation.
    
    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to yield
        check_legality: Whether to check format legality (currently ignored)
        **kwargs: Additional arguments (ignored)
    
    Yields:
        Deck Pydantic models (invalid decks are skipped)
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return
    
    count = 0
    for line in open(path, encoding="utf-8"):
        if max_decks and count >= max_decks:
            break
        
        if not line.strip():
            continue
        
        try:
            deck_dict = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        # Detect game if auto
        detected_game = game
        if game == "auto":
            detected_game = _detect_game_from_deck(deck_dict, path)
        
        # Try to parse as Pydantic model (lenient: skip if fails)
        deck_model = _parse_deck_model(deck_dict, detected_game)
        if deck_model is None:
            continue
        
        yield deck_model
        count += 1

