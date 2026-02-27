#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""
Curriculum sampler: progressive difficulty for annotation batches.

Three phases:
1. Calibration (easy): obvious same-archetype pairs + clearly unrelated pairs.
   Purpose: anchor judge scores, detect systematic bias early.
2. Standard (medium): cross-archetype with shared function, moderate co-occurrence.
   Purpose: bulk training data with good score diversity.
3. Hard (hard): subtle distinctions (hand trap taxonomy, archetype-locked vs generic,
   going-first/second splits).
   Purpose: edge cases that differentiate good from bad embeddings.

Usage:
    from curriculum_sampler import CurriculumSampler
    sampler = CurriculumSampler(edges, card_attrs=card_attrs)
    pairs = sampler.sample(num_pairs=200, phase="auto")
    # phase="auto" uses 20% calibration, 50% standard, 30% hard
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PairDifficulty:
    """A card pair with difficulty metadata."""

    card1: str
    card2: str
    weight: float
    difficulty: str  # "easy", "medium", "hard"
    reason: str  # Why this difficulty level
    expected_score_range: tuple[float, float] = (0.0, 1.0)


@dataclass
class CurriculumSampler:
    """Progressive difficulty pair sampler.

    Classifies pairs into difficulty tiers based on structural properties:
    - Archetype overlap, co-occurrence weight, functional category match.
    """

    edges: list[tuple[str, str, float]]
    card_attrs: dict[str, dict] | None = None
    seed: int = 42
    _rng: random.Random = field(init=False, repr=False)
    _pair_index: dict[tuple[str, str], float] = field(init=False, repr=False)
    _card_to_archetypes: dict[str, set[str]] = field(init=False, repr=False)

    def __post_init__(self):
        self._rng = random.Random(self.seed)
        self._pair_index = {}
        for c1, c2, w in self.edges:
            key = tuple(sorted([c1, c2]))
            self._pair_index[key] = max(self._pair_index.get(key, 0), w)

        # Build archetype index from card names + attributes
        # For YGO: archetype = shared name prefix (e.g., "Ryzeal" in "Ryzeal Detonator")
        # For MTG: archetype from type_line + color
        self._card_to_archetypes = defaultdict(set)
        # Collect all card names from edges for name-based archetype detection
        all_card_names = set()
        for c1, c2, _ in self.edges:
            all_card_names.add(c1)
            all_card_names.add(c2)

        # Extract common prefixes as archetypes (YGO pattern)
        name_prefix_counts: dict[str, int] = Counter()
        for name in all_card_names:
            words = name.split()
            if len(words) >= 2:
                prefix = words[0]
                if len(prefix) >= 3:  # Skip short words like "The", "A"
                    name_prefix_counts[prefix] += 1

        # Prefixes appearing in 3+ cards are likely archetype names
        archetype_prefixes = {p for p, c in name_prefix_counts.items() if c >= 3}

        for name in all_card_names:
            words = name.split()
            for w in words:
                if w in archetype_prefixes:
                    self._card_to_archetypes[name].add(w)

        # Also use card_attrs type_line if available (MTG)
        if self.card_attrs:
            for name, attrs in self.card_attrs.items():
                type_line = attrs.get("type_line", attrs.get("type", ""))
                if type_line and name in all_card_names:
                    # MTG: add color identity and broad type
                    colors = attrs.get("colors", attrs.get("color_identity", ""))
                    if colors:
                        self._card_to_archetypes[name].add(f"color:{colors}")

    def classify_pair(self, c1: str, c2: str, weight: float) -> PairDifficulty:
        """Classify a pair by difficulty based on structural signals."""
        reasons = []

        # Check archetype overlap
        archs1 = self._card_to_archetypes.get(c1, set())
        archs2 = self._card_to_archetypes.get(c2, set())
        arch_overlap = bool(archs1 & archs2) if archs1 and archs2 else None

        # Check functional category from card attributes
        func_match = False
        if self.card_attrs:
            a1 = self.card_attrs.get(c1, {})
            a2 = self.card_attrs.get(c2, {})
            t1 = a1.get("type_line", a1.get("type", "")).lower()
            t2 = a2.get("type_line", a2.get("type", "")).lower()
            # Same broad card type
            if t1 and t2:
                for category in ["monster", "spell", "trap", "creature", "instant", "sorcery",
                                  "enchantment", "artifact", "planeswalker", "pokemon", "trainer", "energy"]:
                    if category in t1 and category in t2:
                        func_match = True
                        break

        # Classify difficulty
        if weight > 20 and arch_overlap is True:
            # High co-occurrence + same archetype = easy (obviously similar)
            return PairDifficulty(c1, c2, weight, "easy",
                                  f"same archetype + high co-occurrence ({weight})",
                                  (0.5, 0.9))

        if weight < 2 and arch_overlap is False:
            # Low co-occurrence + different archetypes = easy (obviously different)
            return PairDifficulty(c1, c2, weight, "easy",
                                  f"different archetypes + low co-occurrence ({weight})",
                                  (0.0, 0.3))

        if weight > 5 and arch_overlap is False and func_match:
            # Cross-archetype but same function = hard (the interesting cases)
            return PairDifficulty(c1, c2, weight, "hard",
                                  f"cross-archetype + same function + co-occur ({weight})",
                                  (0.2, 0.6))

        if weight > 10 and arch_overlap is None:
            # High co-occurrence but unknown archetype = hard (need judge expertise)
            return PairDifficulty(c1, c2, weight, "hard",
                                  f"high co-occurrence ({weight}) but unknown archetype relationship",
                                  (0.3, 0.7))

        if 2 <= weight <= 20:
            # Medium co-occurrence = standard difficulty
            return PairDifficulty(c1, c2, weight, "medium",
                                  f"moderate co-occurrence ({weight})",
                                  (0.1, 0.6))

        # Default: medium
        return PairDifficulty(c1, c2, weight, "medium",
                              f"default classification (weight={weight})",
                              (0.1, 0.7))

    def sample(
        self,
        num_pairs: int = 200,
        phase: str = "auto",
        calibration_frac: float = 0.20,
        standard_frac: float = 0.50,
        hard_frac: float = 0.30,
    ) -> list[PairDifficulty]:
        """Sample pairs with curriculum-based difficulty distribution.

        Args:
            num_pairs: Total pairs to sample.
            phase: "easy", "medium", "hard", or "auto" (mixed).
            calibration_frac: Fraction of easy pairs (phase="auto" only).
            standard_frac: Fraction of medium pairs (phase="auto" only).
            hard_frac: Fraction of hard pairs (phase="auto" only).
        """
        # Classify all edges
        easy, medium, hard = [], [], []
        for c1, c2, w in self.edges:
            p = self.classify_pair(c1, c2, w)
            if p.difficulty == "easy":
                easy.append(p)
            elif p.difficulty == "hard":
                hard.append(p)
            else:
                medium.append(p)

        self._rng.shuffle(easy)
        self._rng.shuffle(medium)
        self._rng.shuffle(hard)

        if phase == "easy":
            return easy[:num_pairs]
        elif phase == "medium":
            return medium[:num_pairs]
        elif phase == "hard":
            return hard[:num_pairs]
        elif phase == "auto":
            n_easy = max(1, int(num_pairs * calibration_frac))
            n_standard = max(1, int(num_pairs * standard_frac))
            n_hard = num_pairs - n_easy - n_standard

            selected = easy[:n_easy] + medium[:n_standard] + hard[:n_hard]

            # Fill shortfalls from other buckets
            deficit = num_pairs - len(selected)
            if deficit > 0:
                remaining = [p for bucket in [medium, easy, hard] for p in bucket
                             if p not in selected]
                selected.extend(remaining[:deficit])

            self._rng.shuffle(selected)
            return selected[:num_pairs]
        else:
            raise ValueError(f"Unknown phase: {phase}. Use 'easy', 'medium', 'hard', or 'auto'.")

    def stats(self) -> dict[str, Any]:
        """Return difficulty distribution statistics."""
        counts = Counter()
        for c1, c2, w in self.edges:
            p = self.classify_pair(c1, c2, w)
            counts[p.difficulty] += 1

        total = sum(counts.values())
        return {
            "total_pairs": total,
            "easy": counts["easy"],
            "medium": counts["medium"],
            "hard": counts["hard"],
            "easy_pct": f"{counts['easy'] / total * 100:.1f}%" if total else "0%",
            "medium_pct": f"{counts['medium'] / total * 100:.1f}%" if total else "0%",
            "hard_pct": f"{counts['hard'] / total * 100:.1f}%" if total else "0%",
        }
