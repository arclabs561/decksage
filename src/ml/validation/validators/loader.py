"""Deck loading and validation utilities.

This module is the *parser boundary* between exported JSONL deck records
(from the backend) and deterministic, game-specific Pydantic models.

Design goal: be explicit and fail-closed (no silent "valid anyway" fallbacks).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .models import MTGDeck, PokemonDeck, YugiohDeck


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
        check_legality: If True, enforce deterministic ban-list legality.
        **kwargs: Additional arguments (ignored)

    Yields:
        Tuples of (deck_model, validation_result) where result has is_valid attribute
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return

    count = 0
    with open(path, encoding="utf-8") as f:
        for _line_num, line in enumerate(f, 1):
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

            if not deck_dict.get("source") and deck_dict.get("url"):
                deck_dict["source"] = _infer_source_from_url(str(deck_dict.get("url") or ""))

            # Detect game if auto
            detected_game = game
            if game == "auto":
                detected_game = _detect_game_from_deck(deck_dict, path)

            if detected_game not in {"magic", "pokemon", "yugioh"}:
                from types import SimpleNamespace

                result = SimpleNamespace(is_valid=False, errors=["Unknown/unsupported game"])
                yield (None, result)
                continue

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

                if check_legality:
                    try:
                        from .legality import check_deck_legality

                        issues = check_deck_legality(deck_model, game=detected_game)
                        if issues:
                            result.is_valid = False
                            result.errors = issues
                    except Exception as e:
                        result.is_valid = False
                        result.errors = [f"legality_check_failed: {e}"]
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
        partitions = [{"name": name, "cards": cards} for name, cards in partitions_dict.items()]

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

        return detect_game(deck=deck_dict, file_path=file_path, default="unknown")
    except ImportError:
        # Minimal fallback (should be rare). Prefer URL over "source" (often null in exports).
        url_or_source = str(deck_dict.get("url") or deck_dict.get("source") or "").lower()
        if "pokemon" in url_or_source or "limitless" in url_or_source:
            return "pokemon"
        if "yugioh" in url_or_source or "ygoprodeck" in url_or_source or "ygo" in url_or_source:
            return "yugioh"
        if any(
            x in url_or_source for x in ["mtgtop8", "mtggoldfish", "deckbox", "scryfall", "mtg"]
        ):
            return "magic"
        return "unknown"


def _parse_deck_model(
    deck_dict: dict[str, Any], game: str
) -> MTGDeck | PokemonDeck | YugiohDeck | None:
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
) -> list[MTGDeck | PokemonDeck | YugiohDeck]:
    """
    Load decks with lenient validation (allows some errors).

    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to load
        check_legality: If True, enforce deterministic ban-list legality (invalid decks skipped)
        verbose: Whether to print progress
        **kwargs: Additional arguments (ignored)

    Returns:
        List of validated deck models. Invalid decks are skipped.
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return []

    decks: list[MTGDeck | PokemonDeck | YugiohDeck] = []
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

                # Ensure "source" is populated if possible (exports often have source=null).
                if not deck_dict.get("source") and deck_dict.get("url"):
                    deck_dict["source"] = _infer_source_from_url(str(deck_dict.get("url") or ""))

                # Detect game if auto
                detected_game = game
                if game == "auto":
                    detected_game = _detect_game_from_deck(deck_dict, path)

                if detected_game not in {"magic", "pokemon", "yugioh"}:
                    skipped += 1
                    if verbose:
                        logger.debug(
                            f"Skipping deck with unknown game at line {line_num}: {deck_dict.get('deck_id', 'unknown')}"
                        )
                    continue

                # Try to parse as Pydantic model (lenient: skip if fails)
                deck_model = _parse_deck_model(deck_dict, detected_game)

                if deck_model is None:
                    skipped += 1
                    if verbose:
                        logger.debug(
                            f"Skipping invalid deck at line {line_num}: {deck_dict.get('deck_id', 'unknown')}"
                        )
                    continue

                # Optional deterministic legality checking (ban lists). If requested,
                # fail-closed: decks with issues are skipped.
                if check_legality:
                    try:
                        from .legality import check_deck_legality

                        issues = check_deck_legality(deck_model, game=detected_game)
                        if issues:
                            skipped += 1
                            if verbose:
                                logger.debug(
                                    "Skipping illegal deck at line %s (%s): %s",
                                    line_num,
                                    deck_dict.get("deck_id", "unknown"),
                                    issues[:3],
                                )
                            continue
                    except Exception as e:
                        skipped += 1
                        if verbose:
                            logger.debug(
                                "Skipping deck due to legality check failure at line %s (%s): %s",
                                line_num,
                                deck_dict.get("deck_id", "unknown"),
                                e,
                            )
                        continue

                # Return Pydantic model (caller may model_dump() if needed)
                decks.append(deck_model)

    except OSError as e:
        logger.error(f"Failed to read deck file {path}: {e}")
        return []

    if verbose:
        logger.info(f"Loaded {len(decks)} decks from {path} (skipped {skipped} invalid)")

    return decks


def load_decks_strict(
    path: Path | str,
    game: str = "auto",
    max_decks: int | None = None,
    check_legality: bool = False,
) -> list[MTGDeck | PokemonDeck | YugiohDeck]:
    """
    Load decks with strict validation (rejects invalid decks).

    Args:
        path: Path to JSONL file
        game: Game name or "auto" for auto-detection
        max_decks: Maximum number of decks to load

    Returns:
        List of validated deck models.

    Raises:
        ValueError on the first invalid record (JSON or schema/validation error).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Deck file not found: {path}")

    decks: list[MTGDeck | PokemonDeck | YugiohDeck] = []

    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if max_decks and len(decks) >= max_decks:
                break
            if not line.strip():
                continue
            try:
                deck_dict = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Line {line_num}: invalid JSON: {e}") from e

            if not deck_dict.get("source") and deck_dict.get("url"):
                deck_dict["source"] = _infer_source_from_url(str(deck_dict.get("url") or ""))

            detected_game = game
            if game == "auto":
                detected_game = _detect_game_from_deck(deck_dict, path)

            if detected_game not in {"magic", "pokemon", "yugioh"}:
                raise ValueError(
                    f"Line {line_num}: could not detect game for deck_id={deck_dict.get('deck_id', 'unknown')}"
                )

            deck_model = _parse_deck_model(deck_dict, detected_game)
            if deck_model is None:
                raise ValueError(
                    f"Line {line_num}: failed to parse/validate deck_id={deck_dict.get('deck_id', 'unknown')}"
                )

            if check_legality:
                from .legality import check_deck_legality

                issues = check_deck_legality(deck_model, game=detected_game)
                if issues:
                    raise ValueError(
                        f"Line {line_num}: illegal deck_id={deck_dict.get('deck_id', 'unknown')}: {issues[:3]}"
                    )
            decks.append(deck_model)

    return decks


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
        check_legality: If True, enforce deterministic ban-list legality (invalid decks skipped)
        **kwargs: Additional arguments (ignored)

    Yields:
        Deck Pydantic models (invalid decks are skipped)
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Deck file not found: {path}")
        return

    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if max_decks and count >= max_decks:
                break

            if not line.strip():
                continue

            try:
                deck_dict = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not deck_dict.get("source") and deck_dict.get("url"):
                deck_dict["source"] = _infer_source_from_url(str(deck_dict.get("url") or ""))

            # Detect game if auto
            detected_game = game
            if game == "auto":
                detected_game = _detect_game_from_deck(deck_dict, path)

            if detected_game not in {"magic", "pokemon", "yugioh"}:
                continue

            # Try to parse as Pydantic model (lenient: skip if fails)
            deck_model = _parse_deck_model(deck_dict, detected_game)
            if deck_model is None:
                continue

            if check_legality:
                try:
                    from .legality import check_deck_legality

                    issues = check_deck_legality(deck_model, game=detected_game)
                    if issues:
                        continue
                except Exception:
                    continue

            yield deck_model
            count += 1
