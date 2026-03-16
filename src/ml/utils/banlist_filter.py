"""Filter co-occurrence edges by format legality.

Uses ban list data to determine whether a card pair is valid in a given format.
Edges where either card is banned/forbidden in the target format are excluded.

Usage:
    from ml.utils.banlist_filter import BanlistFilter

    bf = BanlistFilter.load("magic", "data/banlists/magic_banlists.json")
    filtered = bf.filter_edges(edges, format="modern")
    # Returns only edges where both cards are legal in Modern
"""

from __future__ import annotations

import json
from pathlib import Path


class BanlistFilter:
    """Filter edges by format legality using ban list data."""

    def __init__(self, game: str, banned_by_format: dict[str, set[str]]):
        self.game = game
        # format -> set of banned/forbidden card names
        self.banned_by_format = banned_by_format

    @classmethod
    def load(cls, game: str, banlist_path: str | Path) -> BanlistFilter:
        """Load ban list data from JSON file.

        Expected format (from scrape_banlists.py):
        {
            "game": "magic",
            "formats": {
                "modern": {"banned": ["Card A", ...], "restricted": [...]},
                ...
            }
        }
        """
        path = Path(banlist_path)
        if not path.exists():
            return cls(game, {})

        with open(path) as f:
            data = json.load(f)

        banned_by_format: dict[str, set[str]] = {}
        for fmt, lists in data.get("formats", {}).items():
            banned = set(lists.get("banned", []))
            banned |= set(lists.get("forbidden", []))
            # For YGO: "limited" means restricted to 1 copy, not banned
            # We only filter fully banned/forbidden cards
            banned_by_format[fmt] = banned

        return cls(game, banned_by_format)

    @property
    def available_formats(self) -> list[str]:
        return sorted(self.banned_by_format.keys())

    def is_banned(self, card: str, fmt: str) -> bool:
        """Check if a card is banned in a given format."""
        banned = self.banned_by_format.get(fmt, set())
        return card in banned

    def filter_edges(
        self,
        edges: list[tuple[str, str, float]],
        fmt: str,
    ) -> list[tuple[str, str, float]]:
        """Remove edges where either card is banned in the given format.

        Args:
            edges: List of (card1, card2, weight) tuples.
            fmt: Format name (e.g., "modern", "commander", "tcg").

        Returns:
            Filtered edges where both cards are legal.
        """
        banned = self.banned_by_format.get(fmt, set())
        if not banned:
            return edges  # No ban data = no filtering

        return [(c1, c2, w) for c1, c2, w in edges if c1 not in banned and c2 not in banned]

    def filter_edge_stats(
        self,
        pair_counts: dict[tuple[str, str], float],
        fmt: str,
    ) -> dict[tuple[str, str], float]:
        """Filter pair_counts dict by format legality."""
        banned = self.banned_by_format.get(fmt, set())
        if not banned:
            return pair_counts
        return {
            (c1, c2): w
            for (c1, c2), w in pair_counts.items()
            if c1 not in banned and c2 not in banned
        }

    def stats(self, fmt: str | None = None) -> dict:
        """Return ban list statistics."""
        if fmt:
            banned = self.banned_by_format.get(fmt, set())
            return {"format": fmt, "num_banned": len(banned)}

        return {fmt: len(banned) for fmt, banned in sorted(self.banned_by_format.items())}
