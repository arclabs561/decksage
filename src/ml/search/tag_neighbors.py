"""Inverted tag index for serving-time tag neighbours.

The offline tag arm used the full TagIndex from heuristic_scorers; the API
needs a small, fast query path: for a card, consider only cards that share at
least one tag, score Jaccard, and return the top k.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping


class TagNeighborIndex:
    def __init__(self, card_tags: Mapping[str, Iterable[str]]) -> None:
        self.sets = {name: frozenset(tags) for name, tags in card_tags.items() if tags}
        self.inverted: dict[str, set[str]] = defaultdict(set)
        for name, tags in self.sets.items():
            for tag in tags:
                self.inverted[tag].add(name)

    def top(self, query: str, limit: int = 50) -> list[str]:
        query_tags = self.sets.get(query)
        if not query_tags:
            return []
        candidates: set[str] = set()
        for tag in query_tags:
            candidates |= self.inverted.get(tag, set())
        scored = []
        for card in candidates:
            tags = self.sets[card]
            union = query_tags | tags
            if union:
                scored.append((len(query_tags & tags) / len(union), card))
        scored.sort(reverse=True)
        return [card for _, card in scored[:limit]]

    def __len__(self) -> int:
        return len(self.sets)
