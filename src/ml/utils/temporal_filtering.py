"""
Temporal Filtering for Annotations

Prevents temporal data leakage by filtering annotations based on deck timestamps.
Similar to graph temporal splits, but for annotations.

Critical: Annotations from test-period decks should not be used for training.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def parse_timestamp(ts_str: str | None) -> datetime | None:
    """Parse timestamp from various formats."""
    if not ts_str:
        return None
    
    if isinstance(ts_str, datetime):
        return ts_str
    
    try:
        # ISO format
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        try:
            # Try other common formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(str(ts_str), fmt)
                except ValueError:
                    continue
        except Exception:
            pass
    
    return None


def get_deck_timestamp(deck: dict[str, Any]) -> datetime | None:
    """Extract timestamp from deck dict."""
    for key in ["timestamp", "created_at", "date", "_parsed_timestamp"]:
        if key in deck:
            return parse_timestamp(deck[key])
    return None


def filter_annotations_by_temporal_split(
    annotations: list[dict[str, Any]],
    decks: list[dict[str, Any]],
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    game: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Filter annotations by temporal split to prevent leakage.
    
    Strategy:
    1. Sort decks by timestamp
    2. Split into train/val/test periods
    3. Extract card pairs from each period
    4. Filter annotations: only keep if BOTH cards are from train/val period
    
    Args:
        annotations: List of annotation dicts
        decks: List of deck dicts with timestamps
        train_frac: Training fraction (default: 0.7)
        val_frac: Validation fraction (default: 0.15)
        game: Optional game filter
    
    Returns:
        (train_annotations, filtered_out_annotations, stats_dict)
    """
    # Filter decks by game if specified
    if game:
        decks = [d for d in decks if d.get("game", "").lower() == game.lower()]
    
    # Sort decks by timestamp
    decks_with_ts = []
    for deck in decks:
        ts = get_deck_timestamp(deck)
        if ts:
            decks_with_ts.append((ts, deck))
    
    if not decks_with_ts:
        logger.warning("No decks with timestamps found - cannot apply temporal filtering")
        return annotations, [], {"error": "no_timestamps"}
    
    decks_with_ts.sort(key=lambda x: x[0])
    
    # Compute split points
    n = len(decks_with_ts)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    
    train_decks = [d for _, d in decks_with_ts[:train_end]]
    val_decks = [d for _, d in decks_with_ts[train_end:val_end]]
    test_decks = [d for _, d in decks_with_ts[val_end:]]
    
    # Extract cards from train/val periods (allowed for training)
    train_val_cards = set()
    for deck in train_decks + val_decks:
        for card in deck.get("cards", []):
            if isinstance(card, dict):
                card_name = card.get("name", "")
            else:
                card_name = str(card)
            if card_name:
                train_val_cards.add(card_name)
    
    # Extract cards from test period (must be excluded)
    test_cards = set()
    for deck in test_decks:
        for card in deck.get("cards", []):
            if isinstance(card, dict):
                card_name = card.get("name", "")
            else:
                card_name = str(card)
            if card_name:
                test_cards.add(card_name)
    
    # Filter annotations: only keep if both cards are in train/val period
    train_annotations = []
    filtered_out = []
    
    for ann in annotations:
        card1 = ann.get("card1", "")
        card2 = ann.get("card2", "")
        
        # Check if either card is in test period
        if card1 in test_cards or card2 in test_cards:
            filtered_out.append(ann)
        elif card1 in train_val_cards and card2 in train_val_cards:
            train_annotations.append(ann)
        else:
            # Card not found in any period (might be from different game or missing)
            # Include it but log warning
            logger.debug(f"Card pair not found in temporal split: {card1} vs {card2}")
            train_annotations.append(ann)
    
    stats = {
        "total_annotations": len(annotations),
        "train_val_annotations": len(train_annotations),
        "filtered_out": len(filtered_out),
        "train_decks": len(train_decks),
        "val_decks": len(val_decks),
        "test_decks": len(test_decks),
        "train_val_cards": len(train_val_cards),
        "test_cards": len(test_cards),
    }
    
    if filtered_out:
        logger.warning(
            f"Temporal filtering: Removed {len(filtered_out)} annotations "
            f"containing test-period cards. Remaining: {len(train_annotations)}"
        )
    
    return train_annotations, filtered_out, stats


def load_decks_for_temporal_filtering(
    deck_paths: list[Path] | None = None,
    game: str | None = None,
) -> list[dict[str, Any]]:
    """Load decks for temporal filtering.
    
    Args:
        deck_paths: Optional list of deck file paths
        game: Optional game filter
    
    Returns:
        List of deck dicts
    """
    if deck_paths is None:
        from .paths import PATHS
        deck_paths = [
            PATHS.decks_with_metadata,
            PATHS.decks_all_final,
            PATHS.decks_all_enhanced,
        ]
    
    decks = []
    for deck_path in deck_paths:
        if not deck_path.exists():
            continue
        
        try:
            with open(deck_path) as f:
                for line in f:
                    if line.strip():
                        try:
                            deck = json.loads(line)
                            # Filter by game if specified
                            if game and deck.get("game", "").lower() != game.lower():
                                continue
                            decks.append(deck)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning(f"Failed to load decks from {deck_path}: {e}")
    
    return decks

