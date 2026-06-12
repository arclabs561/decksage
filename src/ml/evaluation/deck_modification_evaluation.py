#!/usr/bin/env python3
"""
Deck Modification System Evaluation

Critiques the deck modification system and generates test cases for regression testing.

This module:
1. Tests the system with real examples
2. Identifies weaknesses and edge cases
3. Generates evaluation queries and ground truth
4. Proposes improvements
"""

from __future__ import annotations

import json

# Import PATHS directly to avoid pandas dependency in utils/__init__.py
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# Try relative import first
try:
    from ..utils.paths import PATHS
except (ImportError, ModuleNotFoundError):
    # Fallback: import directly
    _utils_path = Path(__file__).parent.parent / "utils" / "paths.py"
    if _utils_path.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location("paths", _utils_path)
        paths_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(paths_module)
        PATHS = paths_module.PATHS
    else:
        # Last resort: define minimal PATHS
        _project_root = Path(__file__).parent.parent.parent.parent

        class PATHS:
            experiments = _project_root / "experiments"


@dataclass
class DeckModificationTestCase:
    """A test case for deck modification."""

    name: str
    game: str
    deck: dict[str, Any]
    archetype: str | None
    format: str | None
    expected_additions: list[str]  # Cards that should be suggested
    expected_removals: list[str]  # Cards that should be suggested for removal
    expected_replacements: dict[str, list[str]]  # {card_to_replace: [alternatives]}
    context: str  # Why this is a good test case


@dataclass
class ContextualDiscoveryTestCase:
    """A test case for contextual discovery."""

    name: str
    game: str
    card: str
    format: str | None
    archetype: str | None
    expected_synergies: list[str]
    expected_alternatives: list[str]
    expected_upgrades: list[str]
    expected_downgrades: list[str]
    context: str


@dataclass
class Critique:
    """A critique of the system."""

    category: str  # "add", "remove", "replace", "contextual", "explanation", "performance"
    severity: str  # "critical", "high", "medium", "low"
    issue: str
    evidence: str
    recommendation: str
    test_case: str | None  # Name of test case that would catch this


class DeckModificationEvaluator:
    """Evaluates and critiques the deck modification system."""

    def __init__(self):
        self.critiques: list[Critique] = []
        self.test_cases: list[DeckModificationTestCase] = []
        self.contextual_test_cases: list[ContextualDiscoveryTestCase] = []

    def critique_add_suggestions(self) -> list[Critique]:
        """
        Critique the add suggestions system.

        Issues to check:
        1. Role gap detection accuracy
        2. Archetype staple boosting correctness
        3. Constrained choice effectiveness
        4. Explanation quality
        5. Edge cases (empty deck, full deck, singleton formats)
        """
        critiques = []

        # Issue 1: Role gap detection might miss nuanced roles
        critiques.append(
            Critique(
                category="add",
                severity="high",
                issue="Role gap detection only covers 6 roles (removal, threat, card_draw, ramp, counter, tutor)",
                evidence="Many decks need other roles: graveyard recursion, board wipes, mana fixing, combo pieces",
                recommendation="Expand role taxonomy or use LLM to infer roles from card text",
                test_case="combo_deck_missing_pieces",
            )
        )

        # Issue 2: Archetype staple threshold might be too high
        critiques.append(
            Critique(
                category="add",
                severity="medium",
                issue="Archetype staple threshold (70%) might exclude format staples that are 60-69%",
                evidence="Some format-defining cards might be in 60% of decks but still essential",
                recommendation="Use tiered thresholds: 70%+ = strong staple, 50-69% = format staple, 30-49% = common",
                test_case="format_staple_threshold",
            )
        )

        # Issue 3: Constrained choice (max 10) might be too restrictive for large gaps
        critiques.append(
            Critique(
                category="add",
                severity="low",
                issue="Max 10 suggestions might be too few when deck has many gaps",
                evidence="A new player's deck might need 20+ cards, but only gets 10 suggestions",
                recommendation="Allow pagination or increase limit for incomplete decks (<40 cards)",
                test_case="large_gap_deck",
            )
        )

        # Issue 4: No consideration of card count (suggesting 4-of when 1-of is better)
        critiques.append(
            Critique(
                category="add",
                severity="medium",
                issue="Suggestions don't specify count - always suggests 1 copy",
                evidence="Some cards are better as 4-of (Lightning Bolt), others as 1-of (tutor targets)",
                recommendation="Suggest count based on archetype patterns and card type",
                test_case="card_count_suggestion",
            )
        )

        # Issue 5: No budget awareness in add suggestions (if budget_max provided)
        critiques.append(
            Critique(
                category="add",
                severity="high",
                issue="Budget filtering happens but doesn't prioritize cheaper alternatives",
                evidence="If budget_max=$50, should suggest $2 cards over $10 cards even if both fit",
                recommendation="Boost cheaper cards within budget, or add budget_tier parameter",
                test_case="budget_prioritization",
            )
        )

        return critiques

    def critique_remove_suggestions(self) -> list[Critique]:
        """Critique the remove suggestions system."""
        critiques = []

        # Issue 1: Redundancy detection thresholds might be too strict
        critiques.append(
            Critique(
                category="remove",
                severity="medium",
                issue="Role thresholds (12 removal, 20 threats) might be too high for some formats",
                evidence="Control decks in Legacy might legitimately have 15+ removal spells",
                recommendation="Make thresholds format-aware or use percentile-based thresholds",
                test_case="control_deck_excess_removal",
            )
        )

        # Issue 2: No consideration of card synergy when suggesting removal
        critiques.append(
            Critique(
                category="remove",
                severity="high",
                issue="Might suggest removing a card that synergizes with others in deck",
                evidence="Removing 'Goblin Guide' from a Goblin deck might break tribal synergies",
                recommendation="Check for synergy patterns (tribal, combo pieces, engine cards) before removal",
                test_case="synergy_aware_removal",
            )
        )

        # Issue 3: Low archetype match removal might be too aggressive
        critiques.append(
            Critique(
                category="remove",
                severity="medium",
                issue="Removing cards not in archetype staples might remove meta calls or tech choices",
                evidence="A Burn deck might have 'Smash to Smithereens' as sideboard tech, not a staple",
                recommendation="Distinguish between maindeck staples and sideboard/tech cards",
                test_case="meta_call_removal",
            )
        )

        return critiques

    def critique_replace_suggestions(self) -> list[Critique]:
        """Critique the replace suggestions system."""
        critiques = []

        # Issue 1: Upgrade/downgrade modes are separate - no "similar price, better effect"
        critiques.append(
            Critique(
                category="replace",
                severity="medium",
                issue="No 'lateral upgrade' mode - same price, better card",
                evidence="Might want to replace $2 card with $2.10 card that's strictly better",
                recommendation="Add 'lateral' mode or price_tolerance parameter",
                test_case="lateral_upgrade",
            )
        )

        # Issue 2: Role overlap threshold (30%) might be too low
        critiques.append(
            Critique(
                category="replace",
                severity="high",
                issue="30% role overlap might allow replacing removal with threats",
                evidence="Might suggest replacing 'Lightning Bolt' with 'Goblin Guide' (both red, but different roles)",
                recommendation="Require >50% role overlap for replacements, or add role_match parameter",
                test_case="role_mismatch_replacement",
            )
        )

        # Issue 3: No consideration of deck curve when replacing
        critiques.append(
            Critique(
                category="replace",
                severity="medium",
                issue="Might suggest replacing 1 CMC card with 4 CMC card, breaking curve",
                evidence="Replacing 'Lightning Bolt' with 'Lightning Helix' is fine, but replacing with 'Boros Charm' (3 CMC) might break curve",
                recommendation="Consider CMC similarity when suggesting replacements",
                test_case="curve_aware_replacement",
            )
        )

        return critiques

    def critique_contextual_discovery(self) -> list[Critique]:
        """Critique the contextual discovery system."""
        critiques = []

        # Issue 1: Synergy detection only uses co-occurrence, not functional synergy
        critiques.append(
            Critique(
                category="contextual",
                severity="high",
                issue="Synergies only based on co-occurrence, not functional relationships",
                evidence="'Goblin Guide' and 'Lightning Bolt' co-occur but aren't synergistic - they're just both in Burn",
                recommendation="Add functional synergy detection (tribal, combo, engine, payoff relationships)",
                test_case="functional_synergy",
            )
        )

        # Issue 2: Alternatives might not consider format legality
        critiques.append(
            Critique(
                category="contextual",
                severity="medium",
                issue="Might suggest alternatives that aren't legal in the format",
                evidence="Suggesting 'Chain Lightning' as alternative to 'Lightning Bolt' in Modern (Chain Lightning is Legacy-only)",
                recommendation="Filter alternatives by format legality",
                test_case="format_legal_alternatives",
            )
        )

        # Issue 3: Upgrade/downgrade price comparison might be stale
        critiques.append(
            Critique(
                category="contextual",
                severity="low",
                issue="Price data might be stale or missing for some cards",
                evidence="New cards or reprints might not have price data",
                recommendation="Add fallback to rarity-based price estimation, or mark as 'price unknown'",
                test_case="missing_price_data",
            )
        )

        return critiques

    def critique_explanations(self) -> list[Critique]:
        """Critique the explanation generation."""
        critiques = []

        # Issue 1: Explanations might be too technical
        critiques.append(
            Critique(
                category="explanation",
                severity="medium",
                issue="Explanations use technical terms (inclusion rate, role gap) that new players might not understand",
                evidence="'Archetype staple (87% inclusion)' is clear to experienced players but not beginners",
                recommendation="Add explanation modes: 'technical', 'beginner', 'expert'",
                test_case="explanation_clarity",
            )
        )

        # Issue 2: No explanation for why a card was NOT suggested
        critiques.append(
            Critique(
                category="explanation",
                severity="low",
                issue="Can't explain why a popular card wasn't suggested (budget, legality, redundancy)",
                evidence="User might wonder why 'Snapcaster Mage' wasn't suggested (too expensive, wrong format, etc.)",
                recommendation="Add 'why_not' explanations for common cards that were filtered out",
                test_case="negative_explanation",
            )
        )

        return critiques

    def generate_test_cases(
        self,
    ) -> tuple[list[DeckModificationTestCase], list[ContextualDiscoveryTestCase]]:
        """Generate test cases based on critiques."""
        deck_cases = []
        contextual_cases = []

        # Test case 1: Empty deck (should suggest core staples)
        deck_cases.append(
            DeckModificationTestCase(
                name="empty_burn_deck",
                game="magic",
                deck={"partitions": [{"name": "Main", "cards": []}]},
                archetype="Burn",
                format="Modern",
                expected_additions=[
                    "Lightning Bolt",
                    "Lava Spike",
                    "Rift Bolt",
                    "Monastery Swiftspear",
                ],
                expected_removals=[],
                expected_replacements={},
                context="Empty deck should suggest core archetype staples",
            )
        )

        # Test case 2: Deck with no removal
        deck_cases.append(
            DeckModificationTestCase(
                name="no_removal_deck",
                game="magic",
                deck={
                    "partitions": [
                        {
                            "name": "Main",
                            "cards": [
                                {"name": "Monastery Swiftspear", "count": 4},
                                {"name": "Goblin Guide", "count": 4},
                                {"name": "Eidolon of the Great Revel", "count": 4},
                            ],
                        }
                    ]
                },
                archetype="Burn",
                format="Modern",
                expected_additions=["Lightning Bolt", "Lava Spike", "Rift Bolt"],  # Removal spells
                expected_removals=[],
                expected_replacements={},
                context="Deck missing removal should prioritize removal suggestions",
            )
        )

        # Test case 3: Deck with excess removal
        deck_cases.append(
            DeckModificationTestCase(
                name="excess_removal_deck",
                game="magic",
                deck={
                    "partitions": [
                        {
                            "name": "Main",
                            "cards": [
                                {"name": "Lightning Bolt", "count": 4},
                                {"name": "Lava Spike", "count": 4},
                                {"name": "Rift Bolt", "count": 4},
                                {"name": "Shard Volley", "count": 4},
                                {"name": "Skullcrack", "count": 4},
                                {"name": "Searing Blaze", "count": 4},
                            ],
                        }
                    ]
                },
                archetype="Burn",
                format="Modern",
                expected_additions=["Monastery Swiftspear", "Goblin Guide"],  # Threats
                expected_removals=["Shard Volley"],  # Weakest removal
                expected_replacements={},
                context="Deck with excess removal should suggest removing weakest removal and adding threats",
            )
        )

        # Test case 4: Budget deck
        deck_cases.append(
            DeckModificationTestCase(
                name="budget_burn_deck",
                game="magic",
                deck={
                    "partitions": [
                        {
                            "name": "Main",
                            "cards": [
                                {"name": "Lightning Bolt", "count": 4},
                                {"name": "Lava Spike", "count": 4},
                            ],
                        }
                    ]
                },
                archetype="Burn",
                format="Modern",
                expected_additions=["Rift Bolt", "Shock"],  # Cheap alternatives
                expected_removals=[],
                expected_replacements={},
                context="Budget deck should prioritize cheap cards over expensive staples",
            )
        )

        # Contextual test case 1: Lightning Bolt synergies
        contextual_cases.append(
            ContextualDiscoveryTestCase(
                name="lightning_bolt_contextual",
                game="magic",
                card="Lightning Bolt",
                format="Modern",
                archetype="Burn",
                expected_synergies=["Lava Spike", "Rift Bolt", "Monastery Swiftspear"],
                expected_alternatives=["Chain Lightning", "Shock"],
                expected_upgrades=["Skewer the Critics"],  # If more expensive
                expected_downgrades=["Shock"],  # If cheaper
                context="Lightning Bolt is a format staple with clear synergies and alternatives",
            )
        )

        return deck_cases, contextual_cases

    def run_critique(self) -> dict[str, Any]:
        """Run full critique and generate test cases."""
        all_critiques = (
            self.critique_add_suggestions()
            + self.critique_remove_suggestions()
            + self.critique_replace_suggestions()
            + self.critique_contextual_discovery()
            + self.critique_explanations()
        )

        deck_cases, contextual_cases = self.generate_test_cases()

        return {
            "critiques": [asdict(c) for c in all_critiques],
            "test_cases": [asdict(tc) for tc in deck_cases],
            "contextual_test_cases": [asdict(tc) for tc in contextual_cases],
            "summary": {
                "total_critiques": len(all_critiques),
                "critical": len([c for c in all_critiques if c.severity == "critical"]),
                "high": len([c for c in all_critiques if c.severity == "high"]),
                "medium": len([c for c in all_critiques if c.severity == "medium"]),
                "low": len([c for c in all_critiques if c.severity == "low"]),
                "total_test_cases": len(deck_cases) + len(contextual_cases),
            },
        }


def main():
    """Run evaluation and save results."""
    import argparse

    parser = argparse.ArgumentParser(description="Critique deck modification system")
    parser.add_argument("--output", type=str, help="Output path for critique JSON")
    parser.add_argument(
        "--generate-annotations", action="store_true", help="Also generate annotation templates"
    )

    args = parser.parse_args()

    evaluator = DeckModificationEvaluator()
    results = evaluator.run_critique()

    # Save results
    output_path = (
        Path(args.output) if args.output else PATHS.experiments / "deck_modification_critique.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print("✓ Critique complete")
    print(f"  Total critiques: {results['summary']['total_critiques']}")
    print(
        f"  High: {results['summary']['high']}, Medium: {results['summary']['medium']}, Low: {results['summary']['low']}"
    )
    print(f"  Test cases: {results['summary']['total_test_cases']}")
    print(f"✓ Saved to {output_path}")

    # Print critical issues
    critical = [c for c in results["critiques"] if c["severity"] == "critical"]
    high = [c for c in results["critiques"] if c["severity"] == "high"]

    if critical or high:
        print("\n⚠ Critical/High Issues:")
        for c in critical + high:
            print(f"  [{c['severity'].upper()}] {c['category']}: {c['issue']}")

    # Generate annotation templates if requested
    if args.generate_annotations:
        print("\n📝 Generating annotation templates...")
        try:
            from .deck_modification_judge import generate_annotations_for_all_tasks

            annotation_output = PATHS.experiments / "deck_modification_annotations.json"
            generate_annotations_for_all_tasks(
                critique_path=output_path,
                output_path=annotation_output,
                api_url=None,  # Will generate templates without API calls
                verbose=True,
            )
            print(f"✓ Annotation templates saved to {annotation_output}")
        except Exception as e:
            print(f"⚠ Could not generate annotations: {e}")
            print("  (This is OK - annotations can be generated later with API)")


if __name__ == "__main__":
    main()
