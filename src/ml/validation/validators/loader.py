#!/usr/bin/env python3
"""
Validated data loading for ML pipeline.

Loads and validates decks, collecting errors but not blocking on minor issues.
Provides options for strict vs lenient validation modes.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .legality import check_deck_legality
from .models import MTGDeck, PokemonDeck, YugiohDeck


@dataclass
class ValidationResult:
    """Result of deck validation."""

    deck_id: str
    is_valid: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class LoadResult:
    """Result of loading and validating a dataset."""

    decks: list[MTGDeck | YugiohDeck | PokemonDeck]
    validation_results: list[ValidationResult]
    failed_to_parse: int
    schema_violations: int
    legality_issues: int
    total_processed: int
    metrics: dict = field(default_factory=dict)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Loaded {len(self.decks)}/{self.total_processed} decks successfully",
            f"  Parse failures: {self.failed_to_parse}",
            f"  Schema violations: {self.schema_violations}",
            f"  Legality issues: {self.legality_issues}",
        ]

        # Add metrics if available
        if self.metrics:
            lines.append("\nData Quality Metrics:")
            if "empty_format" in self.metrics:
                pct = 100 * self.metrics["empty_format"] / max(self.total_processed, 1)
                lines.append(f"  Empty format: {self.metrics['empty_format']} ({pct:.1f}%)")
            if "empty_archetype" in self.metrics:
                pct = 100 * self.metrics["empty_archetype"] / max(self.total_processed, 1)
                lines.append(f"  Empty archetype: {self.metrics['empty_archetype']} ({pct:.1f}%)")
            if "inferred_source" in self.metrics:
                lines.append(f"  Inferred sources: {self.metrics['inferred_source']}")
            if "error_distribution" in self.metrics:
                lines.append("  Top errors:")
                for err, count in list(self.metrics["error_distribution"].most_common(5)):
                    lines.append(f"    {err}: {count}")

        return "\n".join(lines)


def _infer_source_from_url(url: str) -> str | None:
    """Infer source from URL since source field is null in data."""
    if not url:
        return None

    url_lower = url.lower()

    # MTG sources
    if "mtgtop8" in url_lower:
        return "mtgtop8"
    if "mtggoldfish" in url_lower or "goldfish" in url_lower:
        return "goldfish"
    if "deckbox.org" in url_lower:
        return "deckbox"
    if "scryfall" in url_lower:
        return "scryfall"
    if "moxfield" in url_lower:
        return "moxfield"
    if "archidekt" in url_lower:
        return "archidekt"

    # YGO sources
    if "ygoprodeck" in url_lower:
        return "ygoprodeck"

    # Pokemon sources
    if "limitless" in url_lower:
        return "limitless"
    if "pokemon.com" in url_lower:
        return "pokemon"

    return None


def _detect_game_type(data: dict) -> Literal["magic", "yugioh", "pokemon", "unknown"]:
    """Infer game type from deck data."""
    # Strategy 1: Check source field (most reliable for export-hetero)
    source = data.get("source", "").lower()
    if source:
        if source in ["mtgtop8", "goldfish", "deckbox", "scryfall"]:
            return "magic"
        if source in ["ygoprodeck", "ygoprodeck-tournament"]:
            return "yugioh"
        if source in ["limitless", "limitless-web", "pokemon"]:
            return "pokemon"

    # Strategy 2: Check URL (often contains game identifier)
    url = data.get("url", "").lower()
    if url:
        if any(domain in url for domain in ["mtgtop8", "mtggoldfish", "deckbox.org", "scryfall"]):
            return "magic"
        if "ygoprodeck" in url:
            return "yugioh"
        if "limitless" in url or "pokemon" in url:
            return "pokemon"

    # Strategy 3: Check format field
    format_name = data.get("format", "").lower().strip()
    if format_name:
        # MTG formats
        if format_name in [
            "modern",
            "legacy",
            "vintage",
            "pauper",
            "commander",
            "standard",
            "pioneer",
            "cedh",
            "brawl",
            "historic",
            "alchemy",
        ]:
            return "magic"
        # YGO formats
        if format_name in ["tcg", "ocg"]:
            return "yugioh"
        # Pokemon formats
        if format_name in ["standard", "expanded", "unlimited"]:
            # Could be Pokemon - check other signals
            pass

    # Strategy 4: Check collection type (for Collection format)
    col_type = data.get("type", {})
    if isinstance(col_type, dict):
        type_str = col_type.get("type", "")
        if "YGO" in type_str or "yugioh" in type_str.lower():
            return "yugioh"
        elif "Pokemon" in type_str or "pokemon" in type_str.lower():
            return "pokemon"
        elif "Deck" in type_str or "Set" in type_str or "Cube" in type_str:
            return "magic"

    # Strategy 5: Check partition names (works for both formats)
    partitions = data.get("partitions", [])
    if not partitions:
        # Check if we need to reconstruct from cards (export-hetero)
        cards = data.get("cards", [])
        partition_names = {c.get("partition", "Main") for c in cards} if cards else set()
    else:
        partition_names = {p.get("name", "") for p in partitions}

    if partition_names:
        # YGO has "Extra Deck"
        if "Extra Deck" in partition_names:
            return "yugioh"
        # Pokemon typically just has "Main Deck"
        if partition_names == {"Main Deck"} and format_name in [
            "standard",
            "expanded",
            "unlimited",
        ]:
            return "pokemon"
        # MTG has "Main" and "Sideboard"
        if "Main" in partition_names or "Sideboard" in partition_names:
            return "magic"

    # Strategy 6: Check card names (expensive, use as last resort)
    cards = data.get("cards", [])
    if cards:
        # Sample first few card names
        card_names = [c.get("name", "") for c in cards[:10]]
        # YGO cards often have very long names
        if any(len(name) > 40 for name in card_names):
            return "yugioh"

    # Default to magic (most common in dataset)
    return "magic"


def _normalize_mtg_deck(data: dict) -> dict:
    """Normalize MTG deck data to match Pydantic schema."""

    # Case 1: export-hetero format (flat cards list with partition field)
    if "cards" in data and isinstance(data["cards"], list) and not data.get("partitions"):
        # Reconstruct partitions from flat card list
        partitions_dict = defaultdict(list)
        for card in data["cards"]:
            partition_name = card.get("partition", "Main")
            partitions_dict[partition_name].append({"name": card["name"], "count": card["count"]})

        # Convert to partitions list
        data["partitions"] = [
            {"name": name, "cards": cards} for name, cards in partitions_dict.items()
        ]

        # Handle empty format/archetype (common in export-hetero)
        format_value = data.get("format", "").strip()
        data["format"] = format_value if format_value else "Unknown"

        archetype_value = data.get("archetype", "").strip()
        data["archetype"] = archetype_value if archetype_value else None

    # Case 2: Collection format (nested type structure)
    elif "type" in data and isinstance(data["type"], dict):
        inner = data["type"].get("inner", {})
        data["format"] = inner.get("format", "Unknown")
        data["archetype"] = inner.get("archetype")
        data["player"] = inner.get("player")
        data["event"] = inner.get("event")
        data["placement"] = inner.get("placement")
        data["event_date"] = inner.get("event_date")

    # Ensure deck_id exists
    if "deck_id" not in data:
        data["deck_id"] = data.get("id", "unknown")

    # Ensure format exists and is not empty
    if "format" not in data or not data["format"]:
        data["format"] = "Unknown"

    return data


def _normalize_yugioh_deck(data: dict) -> dict:
    """Normalize Yu-Gi-Oh! deck data."""

    # Case 1: export-hetero format
    if "cards" in data and isinstance(data["cards"], list) and not data.get("partitions"):
        # Reconstruct partitions
        partitions_dict = defaultdict(list)
        for card in data["cards"]:
            partition_name = card.get("partition", "Main Deck")
            partitions_dict[partition_name].append({"name": card["name"], "count": card["count"]})

        data["partitions"] = [
            {"name": name, "cards": cards} for name, cards in partitions_dict.items()
        ]

        # Handle empty format
        format_value = data.get("format", "").strip()
        data["format"] = format_value if format_value else "TCG"

        archetype_value = data.get("archetype", "").strip()
        data["archetype"] = archetype_value if archetype_value else None

    # Case 2: Collection format
    elif "type" in data and isinstance(data["type"], dict):
        inner = data["type"].get("inner", {})
        data["format"] = inner.get("format", "TCG")
        data["archetype"] = inner.get("archetype")
        data["player"] = inner.get("player")
        data["event"] = inner.get("event")
        data["placement"] = inner.get("placement")
        data["event_date"] = inner.get("event_date")

    # Ensure deck_id exists
    if "deck_id" not in data:
        data["deck_id"] = data.get("id", "unknown")

    # Ensure format exists
    if "format" not in data or not data["format"]:
        data["format"] = "TCG"

    return data


def _normalize_pokemon_deck(data: dict) -> dict:
    """Normalize Pokemon deck data."""

    # Case 1: export-hetero format
    if "cards" in data and isinstance(data["cards"], list) and not data.get("partitions"):
        # Reconstruct partitions
        partitions_dict = defaultdict(list)
        for card in data["cards"]:
            partition_name = card.get("partition", "Main Deck")
            partitions_dict[partition_name].append({"name": card["name"], "count": card["count"]})

        data["partitions"] = [
            {"name": name, "cards": cards} for name, cards in partitions_dict.items()
        ]

        # Handle empty format
        format_value = data.get("format", "").strip()
        data["format"] = format_value if format_value else "Standard"

        archetype_value = data.get("archetype", "").strip()
        data["archetype"] = archetype_value if archetype_value else None

    # Case 2: Collection format
    elif "type" in data and isinstance(data["type"], dict):
        inner = data["type"].get("inner", {})
        data["format"] = inner.get("format", "Standard")
        data["archetype"] = inner.get("archetype")
        data["player"] = inner.get("player")
        data["event"] = inner.get("event")
        data["placement"] = inner.get("placement")
        data["event_date"] = inner.get("event_date")

    # Ensure deck_id exists
    if "deck_id" not in data:
        data["deck_id"] = data.get("id", "unknown")

    # Ensure format exists
    if "format" not in data or not data["format"]:
        data["format"] = "Standard"

    return data


def iter_decks_validated(
    path: Path,
    *,
    check_legality: bool = False,
    fail_on_schema_error: bool = False,
    game: Literal["magic", "yugioh", "pokemon", "auto"] = "auto",
) -> Iterator[tuple[MTGDeck | YugiohDeck | PokemonDeck, ValidationResult]]:
    """
    Stream decks without loading all into memory.

    Yields (deck, validation_result) tuples.
    Use this for large datasets (1M+ decks).
    """
    # Resolve path robustly across different working directories
    rp = _resolve_dataset_path(path)
    with open(rp) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            # Parse JSON
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                if fail_on_schema_error:
                    raise
                yield (
                    None,
                    ValidationResult(
                        deck_id=f"line_{line_num}",
                        is_valid=False,
                        errors=[f"JSON parse error: {e}"],
                        warnings=[],
                    ),
                )
                continue

            # Infer source if null
            if not data.get("source"):
                inferred = _infer_source_from_url(data.get("url", ""))
                if inferred:
                    data["source"] = inferred

            # Detect game type
            game_type = _detect_game_type(data) if game == "auto" else game

            # Normalize and validate
            try:
                if game_type == "magic":
                    data = _normalize_mtg_deck(data)
                    deck = MTGDeck.model_validate(data)
                elif game_type == "yugioh":
                    data = _normalize_yugioh_deck(data)
                    deck = YugiohDeck.model_validate(data)
                elif game_type == "pokemon":
                    data = _normalize_pokemon_deck(data)
                    deck = PokemonDeck.model_validate(data)
                else:
                    if fail_on_schema_error:
                        raise ValueError(f"Unknown game type: {game_type}")
                    yield (
                        None,
                        ValidationResult(
                            deck_id=data.get("deck_id", f"line_{line_num}"),
                            is_valid=False,
                            errors=[f"Unknown game type: {game_type}"],
                            warnings=[],
                        ),
                    )
                    continue

            except ValidationError as e:
                if fail_on_schema_error:
                    raise
                errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                yield (
                    None,
                    ValidationResult(
                        deck_id=data.get("deck_id", f"line_{line_num}"),
                        is_valid=False,
                        errors=errors,
                        warnings=[],
                    ),
                )
                continue

            # Optional legality check
            legality_errors = []
            if check_legality:
                legality_errors = check_deck_legality(deck)

            validation_result = ValidationResult(
                deck_id=deck.deck_id,
                is_valid=len(legality_errors) == 0,
                errors=legality_errors,
                warnings=[],
            )

            yield deck, validation_result


def load_decks_validated(
    path: Path,
    *,
    check_legality: bool = False,
    fail_on_schema_error: bool = False,
    game: Literal["magic", "yugioh", "pokemon", "auto"] = "auto",
    max_decks: int | None = None,
    collect_metrics: bool = True,
) -> LoadResult:
    """
    Load and validate decks from JSONL file.

    Args:
        path: Path to JSONL file
        check_legality: Run expensive legality checks (ban lists, etc)
        fail_on_schema_error: Raise exception on first schema violation
        game: Game type or "auto" to detect
        max_decks: Limit number of decks to load (for testing)
        collect_metrics: Track detailed metrics (default True)

    Returns:
        LoadResult with validated decks and error summary
    """
    decks = []
    validation_results = []
    failed_to_parse = 0
    schema_violations = 0
    legality_issues = 0
    total_processed = 0

    # Metrics collection
    metrics = {} if collect_metrics else None
    if collect_metrics:
        metrics = {
            "empty_format": 0,
            "empty_archetype": 0,
            "empty_source": 0,
            "inferred_source": Counter(),
            "error_distribution": Counter(),
            "game_types": Counter(),
            "formats": Counter(),
        }

    # Resolve path robustly across different working directories
    rp = _resolve_dataset_path(path)
    with open(rp) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            if max_decks and total_processed >= max_decks:
                break

            total_processed += 1

            # Parse JSON
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                failed_to_parse += 1
                if collect_metrics:
                    metrics["error_distribution"]["json_parse"] += 1
                validation_results.append(
                    ValidationResult(
                        deck_id=f"line_{line_num}",
                        is_valid=False,
                        errors=[f"JSON parse error: {e}"],
                        warnings=[],
                    )
                )
                continue

            # Collect metadata metrics
            if collect_metrics:
                if not data.get("format") or data.get("format") == "":
                    metrics["empty_format"] += 1
                if not data.get("archetype") or data.get("archetype") == "":
                    metrics["empty_archetype"] += 1
                if not data.get("source"):
                    metrics["empty_source"] += 1

            # Infer source from URL if null
            if not data.get("source"):
                inferred = _infer_source_from_url(data.get("url", ""))
                if inferred:
                    data["source"] = inferred
                    if collect_metrics:
                        metrics["inferred_source"][inferred] += 1

            # Detect game type
            game_type = _detect_game_type(data) if game == "auto" else game

            if collect_metrics:
                metrics["game_types"][game_type] += 1

            # Normalize data structure
            try:
                if game_type == "magic":
                    data = _normalize_mtg_deck(data)
                    deck = MTGDeck.model_validate(data)
                elif game_type == "yugioh":
                    data = _normalize_yugioh_deck(data)
                    deck = YugiohDeck.model_validate(data)
                elif game_type == "pokemon":
                    data = _normalize_pokemon_deck(data)
                    deck = PokemonDeck.model_validate(data)
                else:
                    schema_violations += 1
                    validation_results.append(
                        ValidationResult(
                            deck_id=data.get("deck_id", f"line_{line_num}"),
                            is_valid=False,
                            errors=[f"Unknown game type: {game_type}"],
                            warnings=[],
                        )
                    )
                    continue

            except ValidationError as e:
                schema_violations += 1
                errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]

                if collect_metrics:
                    # Track error types
                    for err in e.errors():
                        error_type = err["type"]
                        metrics["error_distribution"][error_type] += 1

                validation_results.append(
                    ValidationResult(
                        deck_id=data.get("deck_id", f"line_{line_num}"),
                        is_valid=False,
                        errors=errors,
                        warnings=[],
                    )
                )

                if fail_on_schema_error:
                    raise

                continue

            # Track format distribution
            if collect_metrics:
                metrics["formats"][deck.format] += 1

            # Optional: Check format legality
            legality_errors = []
            if check_legality:
                legality_errors = check_deck_legality(deck)
                if legality_errors:
                    legality_issues += 1

            # Record validation result
            validation_results.append(
                ValidationResult(
                    deck_id=deck.deck_id,
                    is_valid=len(legality_errors) == 0,
                    errors=legality_errors,
                    warnings=[],
                )
            )

            decks.append(deck)

    return LoadResult(
        decks=decks,
        validation_results=validation_results,
        failed_to_parse=failed_to_parse,
        schema_violations=schema_violations,
        legality_issues=legality_issues,
        total_processed=total_processed,
        metrics=metrics or {},
    )


def _resolve_dataset_path(path: Path) -> Path:
    """Resolve dataset path across typical repo layouts.

    Tries the provided path, then project-root joined path.
    """
    p = Path(path)
    if p.exists():
        return p
    # Project root = src/ml/validators/ -> parents[3]
    try:
        proj_root = Path(__file__).resolve().parents[3]
    except Exception:
        proj_root = Path.cwd()
    candidates = [proj_root / p, proj_root / str(p)]
    for c in candidates:
        if c.exists():
            return c
    return p


def load_decks_strict(
    path: Path,
    *,
    check_legality: bool = True,
    game: Literal["magic", "yugioh", "pokemon", "auto"] = "auto",
    max_decks: int | None = None,
) -> list[MTGDeck | YugiohDeck | PokemonDeck]:
    """
    Load decks with strict validation - fails on any error.

    Raises:
        ValidationError: On first validation failure
        ValueError: On JSON parse failure or legality issue
    """
    result = load_decks_validated(
        path,
        check_legality=check_legality,
        fail_on_schema_error=True,
        game=game,
        max_decks=max_decks,
    )

    # Check for legality issues
    if check_legality:
        for vr in result.validation_results:
            if not vr.is_valid:
                raise ValueError(f"Deck {vr.deck_id} has legality issues: {vr.errors}")

    return result.decks


def load_decks_lenient(
    path: Path,
    *,
    check_legality: bool = False,
    game: Literal["magic", "yugioh", "pokemon", "auto"] = "auto",
    max_decks: int | None = None,
    verbose: bool = True,
) -> list[MTGDeck | YugiohDeck | PokemonDeck]:
    """
    Load decks with lenient validation - skip invalid decks, log errors.

    This is the recommended mode for ML pipelines where you want to
    maximize data usage and handle imperfect data gracefully.
    """
    result = load_decks_validated(
        path,
        check_legality=check_legality,
        fail_on_schema_error=False,
        game=game,
        max_decks=max_decks,
    )

    if verbose:
        print(result.summary())

        # Show sample errors
        if result.schema_violations > 0:
            print("\nSample schema violations:")
            for vr in result.validation_results[:5]:
                if not vr.is_valid and vr.errors:
                    print(f"  {vr.deck_id}: {vr.errors[0]}")

        if result.legality_issues > 0:
            print("\nSample legality issues:")
            count = 0
            for vr in result.validation_results:
                if not vr.is_valid and vr.errors and count < 5:
                    print(f"  {vr.deck_id}: {vr.errors[0]}")
                    count += 1

    return result.decks


def stream_decks_lenient(
    path: Path,
    *,
    check_legality: bool = False,
    game: Literal["magic", "yugioh", "pokemon", "auto"] = "auto",
) -> Iterator[MTGDeck | YugiohDeck | PokemonDeck]:
    """
    Stream decks without loading all into memory.

    Use for very large datasets (1M+ decks) to avoid memory issues.
    Only yields valid decks (invalid decks skipped).
    """
    for deck, validation_result in iter_decks_validated(
        path,
        check_legality=check_legality,
        fail_on_schema_error=False,
        game=game,
    ):
        if deck is not None and validation_result.is_valid:
            yield deck
