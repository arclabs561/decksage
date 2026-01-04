"""Krippendorff's Alpha for inter-annotator agreement calculation."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np


def krippendorff_alpha(
    data: list[list[Any]],
    level_of_measurement: str = "nominal",
) -> float:
    """
    Calculate Krippendorff's Alpha for inter-annotator agreement.

    Args:
        data: List of lists, where each inner list is one annotator's labels
              for the same items. Items can be strings, numbers, etc.
        level_of_measurement: "nominal", "ordinal", "interval", or "ratio"

    Returns:
        Alpha value between -1 and 1 (typically 0-1 for good agreement)

    References:
        - Krippendorff, K. (2004). Content Analysis: An Introduction to Its Methodology.
        - https://en.wikipedia.org/wiki/Krippendorff%27s_alpha
    """
    if not data or not data[0]:
        return 0.0

    # Flatten and get all unique values
    all_values = set()
    for annotator_labels in data:
        all_values.update(annotator_labels)

    if len(all_values) < 2:
        # All annotators agree on everything
        return 1.0

    # Convert to numeric codes for easier computation
    value_to_code = {v: i for i, v in enumerate(sorted(all_values))}
    num_values = len(value_to_code)

    # Build coincidence matrix
    # For each item position, count co-occurrences of values
    num_items = len(data[0])
    num_annotators = len(data)

    # Coincidence matrix: value_i x value_j
    coincidence = np.zeros((num_values, num_values))

    for item_idx in range(num_items):
        # Get all values for this item across annotators
        item_values = [data[ann_idx][item_idx] for ann_idx in range(num_annotators)]
        value_counts = Counter(item_values)

        # Count pairs (including self-pairs)
        for val1, count1 in value_counts.items():
            code1 = value_to_code[val1]
            for val2, count2 in value_counts.items():
                code2 = value_to_code[val2]
                if val1 == val2:
                    # Self-pair: count * (count - 1)
                    coincidence[code1, code2] += count1 * (count1 - 1)
                else:
                    # Cross-pair: count1 * count2
                    coincidence[code1, code2] += count1 * count2

    # Normalize by number of pairs
    total_pairs = num_annotators * (num_annotators - 1) * num_items
    if total_pairs > 0:
        coincidence = coincidence / total_pairs

    # Calculate expected coincidence (marginal probabilities)
    marginal = coincidence.sum(axis=1)

    # Calculate observed agreement
    observed = np.trace(coincidence)

    # Calculate expected agreement
    expected = np.sum(marginal**2)

    # Calculate alpha
    if expected == 1.0:
        # Perfect agreement expected (all annotators always agree)
        return 1.0

    alpha = 1.0 - (1.0 - observed) / (1.0 - expected)

    return float(alpha)


def compute_iaa_for_labels(
    judgments: list[dict[str, list[str]]],
    relevance_levels: list[str] | None = None,
) -> dict[str, Any]:
    """
    Compute IAA metrics for multi-judge label generation.

    Args:
        judgments: List of judgment dicts, each with relevance levels as keys
        relevance_levels: List of relevance level names (default: standard 5 levels)

    Returns:
        Dict with IAA metrics including Krippendorff's Alpha
    """
    if relevance_levels is None:
        relevance_levels = [
            "highly_relevant",
            "relevant",
            "somewhat_relevant",
            "marginally_relevant",
            "irrelevant",
        ]

    if not judgments:
        return {
            "num_judges": 0,
            "krippendorff_alpha": 0.0,
            "agreement_rate": 0.0,
            "num_items": 0,
        }

    # Collect all unique cards across all judgments
    all_cards = set()
    for judgment in judgments:
        for level in relevance_levels:
            all_cards.update(judgment.get(level, []))

    if not all_cards:
        return {
            "num_judges": len(judgments),
            "krippendorff_alpha": 0.0,
            "agreement_rate": 0.0,
            "num_items": 0,
        }

    # For each card, determine which level each judge assigned it to
    # (or "none" if not assigned)
    card_assignments: dict[str, list[str]] = {}

    for card in all_cards:
        assignments = []
        for judgment in judgments:
            assigned_level = "none"
            for level in relevance_levels:
                if card in judgment.get(level, []):
                    assigned_level = level
                    break
            assignments.append(assigned_level)
        card_assignments[card] = assignments

    # Calculate Krippendorff's Alpha
    data_matrix = list(card_assignments.values())
    alpha = krippendorff_alpha(data_matrix, level_of_measurement="ordinal")

    # Calculate simple agreement rate (percentage of cards with majority agreement)
    agreement_scores = []
    for assignments in card_assignments.values():
        from collections import Counter

        counts = Counter(assignments)
        max_count = max(counts.values()) if counts else 0
        agreement = max_count / len(assignments) if assignments else 0.0
        agreement_scores.append(agreement)

    avg_agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.0

    return {
        "num_judges": len(judgments),
        "krippendorff_alpha": alpha,
        "agreement_rate": avg_agreement,
        "num_items": len(all_cards),
    }
