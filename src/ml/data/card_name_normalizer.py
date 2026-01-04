"""Card name normalization for consistent matching across games."""

from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher


def normalize_card_name(name: str) -> str:
    """
    Normalize card name for consistent storage and comparison.

    Handles:
    - Leading/trailing whitespace
    - HTML entity decoding
    - Unicode normalization (NFC)
    - Multiple spaces collapsed to single space
    - Case normalization (lowercase for comparison)
    """
    if not name:
        return ""

    # Trim whitespace
    name = name.strip()

    # Decode HTML entities (e.g., &amp; -> &, &quot; -> ")
    name = html.unescape(name)

    # Unicode normalization (NFC - Canonical Decomposition followed by Canonical Composition)
    name = unicodedata.normalize("NFC", name)

    # Collapse multiple spaces to single space
    name = re.sub(r"\s+", " ", name)

    return name


def normalize_for_comparison(name: str) -> str:
    """
    Normalize card name for case-insensitive comparison.

    Returns lowercase version for matching.
    """
    return normalize_card_name(name).lower()


def get_name_variants(card_name: str) -> list[str]:
    """
    Generate name variants to try for fuzzy matching.

    Handles:
    - Original name
    - Normalized version
    - Without parenthetical content
    - Split cards (//)
    - ASCII-only version
    - Without common suffixes
    """
    variants = [card_name]
    seen = {card_name.lower()}

    # Normalized version
    normalized = normalize_card_name(card_name)
    if normalized.lower() not in seen:
        variants.append(normalized)
        seen.add(normalized.lower())

    # Remove parenthetical content (e.g., "Card Name (Set Name)")
    no_parens = re.sub(r"\s*\([^)]*\)", "", card_name).strip()
    if no_parens and no_parens.lower() not in seen:
        variants.append(no_parens)
        seen.add(no_parens.lower())

    # Remove "//" split cards (take first part, then second part)
    if "//" in card_name:
        parts = [p.strip() for p in card_name.split("//")]
        for part in parts:
            if part and part.lower() not in seen:
                variants.append(part)
                seen.add(part.lower())

    # Try removing special Unicode characters (keep ASCII only)
    ascii_only = "".join(c for c in card_name if ord(c) < 128)
    if ascii_only.strip() and ascii_only.strip().lower() not in seen:
        variants.append(ascii_only.strip())
        seen.add(ascii_only.strip().lower())

    # Try removing common suffixes/prefixes
    for suffix in [" (minigame)", " (cont'd)", " // "]:
        if suffix in card_name:
            cleaned = card_name.replace(suffix, "").strip()
            if cleaned and cleaned.lower() not in seen:
                variants.append(cleaned)
                seen.add(cleaned.lower())

    # Remove trailing punctuation
    cleaned = card_name.rstrip(".,;:!?")
    if cleaned != card_name and cleaned and cleaned.lower() not in seen:
        variants.append(cleaned)
        seen.add(cleaned.lower())

    return variants


def fuzzy_match_card_name(
    query_name: str,
    candidate_names: list[str],
    threshold: float = 0.85,
) -> list[tuple[str, float]]:
    """
    Find fuzzy matches for a card name.

    Returns list of (matched_name, similarity_score) tuples sorted by score.
    """
    query_norm = normalize_for_comparison(query_name)
    matches = []

    for candidate in candidate_names:
        candidate_norm = normalize_for_comparison(candidate)
        similarity = SequenceMatcher(None, query_norm, candidate_norm).ratio()
        if similarity >= threshold:
            matches.append((candidate, similarity))

    return sorted(matches, key=lambda x: x[1], reverse=True)


def find_best_match(
    query_name: str,
    candidate_names: list[str],
    threshold: float = 0.85,
) -> tuple[str | None, float]:
    """
    Find the best matching card name.

    Returns (best_match, score) or (None, 0.0) if no match above threshold.
    """
    matches = fuzzy_match_card_name(query_name, candidate_names, threshold)
    if matches:
        return matches[0]
    return None, 0.0
