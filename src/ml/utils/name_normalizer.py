"""Name normalization utilities for consistent card name matching."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def normalize_card_name(name: str) -> str:
    """Normalize card name for matching."""
    # Remove special characters, lowercase, strip
    normalized = re.sub(r"[^\w\s]", "", name.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def find_name_matches(
    query_name: str,
    candidate_names: list[str],
    threshold: float = 0.8,
) -> list[tuple[str, float]]:
    """Find fuzzy matches for a card name."""
    query_norm = normalize_card_name(query_name)
    matches = []

    for candidate in candidate_names:
        candidate_norm = normalize_card_name(candidate)
        similarity = SequenceMatcher(None, query_norm, candidate_norm).ratio()
        if similarity >= threshold:
            matches.append((candidate, similarity))

    return sorted(matches, key=lambda x: x[1], reverse=True)


class NameMapper:
    """Maps card names between different naming conventions."""

    def __init__(self, mapping: dict[str, str] | None = None, mapping_path: Path | None = None):
        """Initialize with a name mapping."""
        if mapping_path and mapping_path.exists():
            with open(mapping_path) as f:
                data = json.load(f)
                self.mapping = data.get("mapping", {})
        elif mapping:
            self.mapping = mapping
        else:
            self.mapping = {}

    def map_name(self, name: str, fallback_to_original: bool = True) -> str:
        """Map a card name using the mapping."""
        return self.mapping.get(name, name if fallback_to_original else "")

    def map_names(self, names: list[str], fallback_to_original: bool = True) -> list[str]:
        """Map a list of card names."""
        return [self.map_name(name, fallback_to_original) for name in names]

    def has_mapping(self, name: str) -> bool:
        """Check if a name has a mapping."""
        return name in self.mapping

    @classmethod
    def load_from_file(cls, path: Path) -> NameMapper:
        """Load a NameMapper from a JSON file."""
        return cls(mapping_path=path)


def apply_name_mapping_to_test_set(
    test_set: dict[str, dict[str, Any]],
    mapper: NameMapper,
) -> dict[str, dict[str, Any]]:
    """Apply name mapping to a test set."""
    mapped_test_set = {}

    for query, labels in test_set.items():
        mapped_query = mapper.map_name(query)
        mapped_labels = {}

        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            if level in labels:
                mapped_labels[level] = mapper.map_names(labels[level])
            else:
                mapped_labels[level] = []

        mapped_test_set[mapped_query] = mapped_labels

    return mapped_test_set
