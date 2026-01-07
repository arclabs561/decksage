"""Fuzzy matching utilities for card names.

Handles variations in card names for duplicate detection.
"""

from __future__ import annotations

from difflib import SequenceMatcher


def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings.
    
    Returns float in [0, 1] where 1.0 is identical.
    """
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def normalize_for_fuzzy(name: str) -> str:
    """Normalize card name for fuzzy matching.
    
    Removes:
    - Punctuation
    - Extra whitespace
    - Common words (the, a, an)
    """
    if not name:
        return ""
    
    # Lowercase and strip
    normalized = name.lower().strip()
    
    # Remove common punctuation
    for char in ".,;:!?()[]{}'\"-":
        normalized = normalized.replace(char, " ")
    
    # Remove common words
    common_words = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for"}
    words = normalized.split()
    words = [w for w in words if w not in common_words]
    
    return " ".join(words)


def fuzzy_match_card_names(
    name1: str,
    name2: str,
    threshold: float = 0.85,
) -> tuple[bool, float]:
    """Check if two card names are likely the same (fuzzy match).
    
    Args:
        name1: First card name
        name2: Second card name
        threshold: Similarity threshold (0-1), default 0.85
        
    Returns:
        Tuple of (is_match, similarity_ratio)
    """
    # Exact match after normalization
    norm1 = normalize_for_fuzzy(name1)
    norm2 = normalize_for_fuzzy(name2)
    
    if norm1 == norm2:
        return True, 1.0
    
    # Fuzzy similarity
    ratio = similarity_ratio(norm1, norm2)
    return ratio >= threshold, ratio


def find_fuzzy_duplicates(
    annotations: list[dict],
    threshold: float = 0.85,
) -> list[tuple[int, int, float, str, str]]:
    """Find potential duplicate annotations using fuzzy matching.
    
    Args:
        annotations: List of annotation dictionaries
        threshold: Similarity threshold for fuzzy matching
        
    Returns:
        List of (index1, index2, similarity, card1_pair, card2_pair) tuples
        where card1_pair and card2_pair are the card names being compared
    """
    duplicates = []
    
    for i in range(len(annotations)):
        ann1 = annotations[i]
        card1a = ann1.get("card1", "")
        card1b = ann1.get("card2", "")
        
        for j in range(i + 1, len(annotations)):
            ann2 = annotations[j]
            card2a = ann2.get("card1", "")
            card2b = ann2.get("card2", "")
            
            # Check if pairs match (fuzzy)
            match1a_2a, ratio1a_2a = fuzzy_match_card_names(card1a, card2a, threshold)
            match1b_2b, ratio1b_2b = fuzzy_match_card_names(card1b, card2b, threshold)
            
            # Also check swapped
            match1a_2b, ratio1a_2b = fuzzy_match_card_names(card1a, card2b, threshold)
            match1b_2a, ratio1b_2a = fuzzy_match_card_names(card1b, card2a, threshold)
            
            # Check if it's the same pair (either order)
            if (match1a_2a and match1b_2b) or (match1a_2b and match1b_2a):
                avg_ratio = (
                    (ratio1a_2a + ratio1b_2b) / 2
                    if match1a_2a and match1b_2b
                    else (ratio1a_2b + ratio1b_2a) / 2
                )
                pair_str = f"{card1a} <-> {card1b}"
                duplicates.append((i, j, avg_ratio, pair_str, f"{card2a} <-> {card2b}"))
    
    return duplicates


