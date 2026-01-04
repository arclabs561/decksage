#!/usr/bin/env python3
"""
Deck completion evaluation helpers.

Measures alignment with goals:
- Functional coverage delta (new tags added)
- Curve fit proxy (CMC/type histogram KL divergence placeholder)
- Budget adherence (sum under max)
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple


def functional_coverage_delta(
    before: dict,
    after: dict,
    tag_set_fn: Optional[Callable[[str], set[str]]],
    *,
    main_partition: str,
) -> int:
    if tag_set_fn is None:
        return 0
    def deck_tags(deck) -> set[str]:
        tags: set[str] = set()
        partitions = deck.partitions if hasattr(deck, "partitions") else deck.get("partitions", [])
        for p in partitions or []:
            p_dict = p if isinstance(p, dict) else p.model_dump()
            if p_dict.get("name") != main_partition:
                continue
            for c in p_dict.get("cards", []) or []:
                tags |= tag_set_fn(str(c.get("name", "")))
        return tags
    return max(0, len(deck_tags(after) - deck_tags(before)))


def deck_price_total(deck, price_fn: Optional[Callable[[str], Optional[float]]], *, main_partition: str) -> tuple[Optional[float], list[str]]:
    if price_fn is None:
        return None, []
    total = 0.0
    missing = []
    partitions = deck.partitions if hasattr(deck, "partitions") else deck.get("partitions", [])
    for p in partitions or []:
        p_dict = p if isinstance(p, dict) else p.model_dump()
        if p_dict.get("name") != main_partition:
            continue
        for c in p_dict.get("cards", []) or []:
            name = str(c.get("name", ""))
            count = int(c.get("count", 0))
            price = price_fn(name)
            if price is None:
                missing.append(name)
                continue
            total += float(price) * count
    return round(total, 2), missing


__all__ = ["functional_coverage_delta", "deck_price_total"]





