#!/usr/bin/env python3
"""
Compute Temporal Metadata for Decks

Post-processing script to compute:
- Days since format rotation
- Days since ban list update
- Meta share at event time

This should be run after scraping to enrich deck metadata.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..data.format_events import get_format_events, get_legal_periods
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def compute_days_since_rotation(
    event_date: str,
    game: str,
    format: str,
) -> int | None:
    """
    Compute days since last format rotation.
    
    Args:
        event_date: Event date in ISO format (YYYY-MM-DD)
        game: Game name ("MTG", "PKM", "YGO")
        format: Format name ("Standard", "Modern", etc.)
    
    Returns:
        Days since last rotation, or None if not applicable
    """
    if not event_date or not game or not format:
        return None
    
    try:
        event_dt = datetime.fromisoformat(event_date)
    except (ValueError, TypeError):
        return None
    
    # Get format events
    events = get_format_events(game, format, end_date=event_dt)
    
    # Find most recent rotation
    rotations = [e for e in events if e.event_type == "rotation"]
    if not rotations:
        return None
    
    last_rotation = max(rotations, key=lambda e: e.date)
    days = (event_dt - last_rotation.date).days
    
    return max(0, days)  # Don't return negative


def compute_days_since_ban_update(
    event_date: str,
    game: str,
    format: str,
) -> int | None:
    """
    Compute days since last ban list update.
    
    Args:
        event_date: Event date in ISO format (YYYY-MM-DD)
        game: Game name ("MTG", "PKM", "YGO")
        format: Format name ("Standard", "Modern", etc.)
    
    Returns:
        Days since last ban update, or None if not applicable
    """
    if not event_date or not game or not format:
        return None
    
    try:
        event_dt = datetime.fromisoformat(event_date)
    except (ValueError, TypeError):
        return None
    
    # Get format events
    events = get_format_events(game, format, end_date=event_dt)
    
    # Find most recent ban update
    bans = [e for e in events if e.event_type == "ban"]
    if not bans:
        return None
    
    last_ban = max(bans, key=lambda e: e.date)
    days = (event_dt - last_ban.date).days
    
    return max(0, days)  # Don't return negative


def compute_meta_share(
    deck: dict[str, Any],
    all_decks: list[dict[str, Any]],
    event_date: str | None = None,
    format: str | None = None,
) -> float | None:
    """
    Compute meta share for a deck at event time.
    
    Meta share = (number of decks with same archetype) / (total decks in tournament/format)
    
    Args:
        deck: Deck dictionary
        all_decks: All decks from same tournament/format
        event_date: Event date for filtering (optional)
        format: Format for filtering (optional)
    
    Returns:
        Meta share (0.0-1.0), or None if cannot compute
    """
    if not all_decks:
        return None
    
    # Filter decks by event date and format if provided
    filtered_decks = all_decks
    if event_date:
        try:
            event_dt = datetime.fromisoformat(event_date)
            # Include decks from same month (approximate tournament window)
            filtered_decks = [
                d for d in filtered_decks
                if d.get("eventDate") or d.get("event_date")
            ]
            # Filter by date range (±30 days)
            filtered_decks = [
                d for d in filtered_decks
                if _is_within_date_range(d.get("eventDate") or d.get("event_date"), event_dt, days=30)
            ]
        except (ValueError, TypeError):
            pass
    
    if format:
        filtered_decks = [
            d for d in filtered_decks
            if (d.get("format") or _extract_format_from_deck(d)) == format
        ]
    
    if not filtered_decks:
        return None
    
    # Get archetype
    archetype = (
        deck.get("archetype")
        or _extract_archetype_from_deck(deck)
    )
    
    if not archetype:
        return None
    
    # Count decks with same archetype
    archetype_count = sum(
        1 for d in filtered_decks
        if (d.get("archetype") or _extract_archetype_from_deck(d)) == archetype
    )
    
    total_count = len(filtered_decks)
    if total_count == 0:
        return None
    
    meta_share = archetype_count / total_count
    return float(meta_share)


def _is_within_date_range(date_str: str | None, target_date: datetime, days: int = 30) -> bool:
    """Check if date is within ±days of target date."""
    if not date_str:
        return False
    try:
        date_dt = datetime.fromisoformat(date_str)
        delta = abs((date_dt - target_date).days)
        return delta <= days
    except (ValueError, TypeError):
        return False


def _extract_format_from_deck(deck: dict[str, Any]) -> str | None:
    """Extract format from deck structure."""
    if "format" in deck:
        return deck["format"]
    if "type" in deck and isinstance(deck["type"], dict):
        inner = deck["type"].get("inner")
        if isinstance(inner, dict) and "format" in inner:
            return inner["format"]
    return None


def _extract_archetype_from_deck(deck: dict[str, Any]) -> str | None:
    """Extract archetype from deck structure."""
    if "archetype" in deck:
        return deck["archetype"]
    if "type" in deck and isinstance(deck["type"], dict):
        inner = deck["type"].get("inner")
        if isinstance(inner, dict) and "archetype" in inner:
            return inner["archetype"]
    return None


def _extract_game_from_deck(deck: dict[str, Any]) -> str | None:
    """Extract game from deck structure."""
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
    game = deck.get("game")
    if game:
        return game_map.get(game.lower())
    # Try to infer from source
    source = deck.get("source", "").lower()
    if "magic" in source or "mtg" in source:
        return "MTG"
    if "pokemon" in source or "limitless" in source:
        return "PKM"
    if "yugioh" in source or "ygo" in source:
        return "YGO"
    return None


def compute_matchup_statistics(
    deck: dict[str, Any],
    all_decks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Compute matchup statistics from round results.
    
    Args:
        deck: Deck dictionary with roundResults
        all_decks: All decks for opponent archetype lookup (optional)
    
    Returns:
        Dict with matchup statistics, or None if no round results
    """
    # Extract round results
    round_results = (
        deck.get("roundResults")
        or (deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}).get("roundResults")
    )
    
    if not round_results or not isinstance(round_results, list):
        return None
    
    # Create lookup for opponent archetypes if all_decks provided
    opponent_archetypes: dict[str, str] = {}
    if all_decks:
        for d in all_decks:
            if not isinstance(d, dict):
                continue
            player = (
                d.get("player")
                or (d.get("type", {}).get("inner", {}) if isinstance(d.get("type"), dict) else {}).get("player")
            )
            archetype = _extract_archetype_from_deck(d)
            if player and archetype:
                opponent_archetypes[player] = archetype
    
    # Filter out invalid round results
    valid_rounds = [
        r for r in round_results
        if isinstance(r, dict) and r.get("result") in ("W", "L", "T", "BYE")
    ]
    
    if not valid_rounds:
        return None
    
    # Compute statistics
    total_rounds = len(valid_rounds)
    wins = sum(1 for r in valid_rounds if r.get("result") == "W")
    losses = sum(1 for r in valid_rounds if r.get("result") == "L")
    ties = sum(1 for r in valid_rounds if r.get("result") == "T")
    byes = sum(1 for r in valid_rounds if r.get("result") == "BYE")
    
    # Matchup win rates by archetype
    matchup_wr = defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0})
    for r in valid_rounds:
        opponent_deck = r.get("opponentDeck") or r.get("opponent_deck")
        if not opponent_deck:
            # Try to look up from opponent name
            opponent = r.get("opponent")
            if opponent and opponent in opponent_archetypes:
                opponent_deck = opponent_archetypes[opponent]
        
        if opponent_deck:
            result = r.get("result")
            if result == "W":
                matchup_wr[opponent_deck]["wins"] += 1
            elif result == "L":
                matchup_wr[opponent_deck]["losses"] += 1
            elif result == "T":
                matchup_wr[opponent_deck]["ties"] += 1
    
    # Convert to win rates
    matchup_win_rates: dict[str, dict[str, Any]] = {}
    for archetype, stats in matchup_wr.items():
        total = stats["wins"] + stats["losses"] + stats["ties"]
        if total > 0:
            matchup_win_rates[archetype] = {
                "win_rate": stats["wins"] / total,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "ties": stats["ties"],
                "total": total,
            }
    
    return {
        "total_rounds": total_rounds,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "byes": byes,
        "win_rate": wins / total_rounds if total_rounds > 0 else 0.0,
        "matchup_win_rates": matchup_win_rates,
    }


def enrich_deck_with_temporal_metadata(
    deck: dict[str, Any],
    all_decks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Enrich a single deck with temporal metadata.
    
    Args:
        deck: Deck dictionary
        all_decks: All decks for meta share computation (optional)
    
    Returns:
        Enriched deck dictionary
    """
    # Extract metadata
    event_date = (
        deck.get("eventDate")
        or deck.get("event_date")
        or (deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}).get("eventDate")
    )
    format_value = _extract_format_from_deck(deck)
    game = _extract_game_from_deck(deck)
    
    # Compute temporal context
    if event_date and game and format_value:
        days_since_rotation = compute_days_since_rotation(event_date, game, format_value)
        days_since_ban = compute_days_since_ban_update(event_date, game, format_value)
        
        # Update deck structure
        if isinstance(deck.get("type"), dict) and isinstance(deck["type"].get("inner"), dict):
            inner = deck["type"]["inner"]
            if days_since_rotation is not None:
                inner["daysSinceRotation"] = days_since_rotation
            if days_since_ban is not None:
                inner["daysSinceBanUpdate"] = days_since_ban
        else:
            # Direct fields
            if days_since_rotation is not None:
                deck["daysSinceRotation"] = days_since_rotation
            if days_since_ban is not None:
                deck["daysSinceBanUpdate"] = days_since_ban
    
    # Compute meta share if all_decks provided
    if all_decks and event_date and format_value:
        meta_share = compute_meta_share(deck, all_decks, event_date, format_value)
        if meta_share is not None:
            if isinstance(deck.get("type"), dict) and isinstance(deck["type"].get("inner"), dict):
                deck["type"]["inner"]["metaShare"] = meta_share
            else:
                deck["metaShare"] = meta_share
    
    # Compute matchup statistics from round results
    matchup_stats = compute_matchup_statistics(deck, all_decks)
    if matchup_stats:
        if isinstance(deck.get("type"), dict) and isinstance(deck["type"].get("inner"), dict):
            deck["type"]["inner"]["matchupStatistics"] = matchup_stats
        else:
            deck["matchupStatistics"] = matchup_stats
    
    return deck


def process_decks_file(
    input_path: Path,
    output_path: Path | None = None,
    compute_meta_share: bool = True,
) -> int:
    """
    Process a JSONL file of decks and enrich with temporal metadata.
    
    Args:
        input_path: Path to input JSONL file
        output_path: Path to output JSONL file (default: overwrite input)
        compute_meta_share: Whether to compute meta share (requires loading all decks)
    
    Returns:
        Number of decks processed
    """
    if output_path is None:
        output_path = input_path
    
    logger.info(f"Loading decks from {input_path}...")
    
    # Load all decks
    all_decks = []
    with open(input_path) as f:
        for line in f:
            if line.strip():
                try:
                    deck = json.loads(line)
                    all_decks.append(deck)
                except json.JSONDecodeError:
                    continue
    
    logger.info(f"Loaded {len(all_decks):,} decks")
    
    # Process each deck
    enriched_count = 0
    with open(output_path, 'w') as f:
        for i, deck in enumerate(all_decks):
            try:
                enriched = enrich_deck_with_temporal_metadata(
                    deck,
                    all_decks if compute_meta_share else None,
                )
                f.write(json.dumps(enriched) + '\n')
                enriched_count += 1
                
                if (i + 1) % 1000 == 0:
                    logger.info(f"  Processed {i + 1:,}/{len(all_decks):,} decks...")
            except Exception as e:
                logger.warning(f"  Failed to enrich deck {i + 1}: {e}")
                # Write original deck if enrichment fails
                f.write(json.dumps(deck) + '\n')
    
    logger.info(f"✓ Enriched {enriched_count:,} decks with temporal metadata")
    return enriched_count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute temporal metadata for decks"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PATHS.processed / "decks_all_final.jsonl",
        help="Input JSONL file with decks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSONL file (default: overwrite input)",
    )
    parser.add_argument(
        "--no-meta-share",
        action="store_true",
        help="Skip meta share computation (faster)",
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1
    
    process_decks_file(
        args.input,
        args.output,
        compute_meta_share=not args.no_meta_share,
    )
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

