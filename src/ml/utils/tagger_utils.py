#!/usr/bin/env python3
"""
Utilities for handling functional tagger results.

Provides consistent handling of tagger results whether they are dataclasses,
regular classes, or dictionaries.
"""

from __future__ import annotations

from typing import Any


def extract_tag_dict(tags_obj: Any) -> dict[str, Any]:
    """
    Extract dictionary from tagger result, handling both dataclasses and regular classes.

    Args:
        tags_obj: Result from tagger.tag_card(), can be:
            - A dataclass instance (e.g., FunctionalTags)
            - A regular class instance with __dict__
            - A dictionary (returned as-is)

    Returns:
        Dictionary of tag fields and values

    Examples:
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Tags:
        ...     card_name: str
        ...     removal: bool = False
        >>> tags = Tags("Lightning Bolt", removal=True)
        >>> extract_tag_dict(tags)
        {'card_name': 'Lightning Bolt', 'removal': True}

        >>> class RegularTags:
        ...     def __init__(self):
        ...         self.card_name = "Bolt"
        ...         self.removal = True
        >>> tags = RegularTags()
        >>> extract_tag_dict(tags)
        {'card_name': 'Bolt', 'removal': True}
    """
    if tags_obj is None:
        return {}

    # If already a dict, return as-is
    if isinstance(tags_obj, dict):
        return tags_obj

    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(tags_obj):
            return asdict(tags_obj)
    except (ImportError, TypeError):
        # Fallback if dataclasses not available or object isn't a dataclass
        pass

    # Fallback to vars() for regular classes
    if hasattr(tags_obj, "__dict__"):
        return vars(tags_obj)

    # Last resort: try to convert to dict using object's attributes
    return {k: getattr(tags_obj, k) for k in dir(tags_obj) if not k.startswith("_")}


def extract_tag_set(tags_obj: Any, exclude_fields: set[str] | None = None) -> set[str]:
    """
    Extract set of active (True) boolean tags from tagger result.

    Args:
        tags_obj: Result from tagger.tag_card()
        exclude_fields: Fields to exclude from tag set (e.g., "card_name")

    Returns:
        Set of tag names that are True

    Examples:
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Tags:
        ...     card_name: str
        ...     removal: bool = True
        ...     draw: bool = False
        >>> tags = Tags("Bolt", removal=True, draw=False)
        >>> extract_tag_set(tags, exclude_fields={"card_name"})
        {'removal'}
    """
    if exclude_fields is None:
        exclude_fields = {"card_name"}

    tag_dict = extract_tag_dict(tags_obj)
    return {
        k
        for k, v in tag_dict.items()
        if k not in exclude_fields and isinstance(v, bool) and v
    }




