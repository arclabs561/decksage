#!/usr/bin/env python3
"""
Missing Evaluation Dimensions Analysis

Identifies what we're NOT judging but should be, based on:
1. User goals and use cases
2. Real-world deck building scenarios
3. System capabilities vs what we evaluate
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class MissingDimension:
    """A dimension we should be evaluating but aren't."""

    dimension: str
    category: str  # add|remove|replace|contextual|similarity|overall
    importance: str  # critical|high|medium|low
    description: str
    why_missing: str
    how_to_measure: str
    example_test_case: str
    current_coverage: str  # "not_judged" | "partially_judged" | "implicitly_judged"


class MissingDimensionsAnalyzer:
    """Analyzes what evaluation dimensions we're missing."""

    def __init__(self):
        self.current_dimensions = self._get_current_dimensions()
        self.user_goals = self._get_user_goals()
        self.missing: list[MissingDimension] = []

    def _get_current_dimensions(self) -> dict[str, list[str]]:
        """What we currently judge."""
        return {
            "add": [
                "relevance",  # 0-4: How appropriate
                "explanation_quality",  # 0-4: Quality of explanation
                "archetype_match",  # 0-4: Fits archetype
                "role_fit",  # 0-4: Fills role gap
            ],
            "remove": [
                "relevance",  # Should this be removed?
                "reasoning",  # Why remove it?
            ],
            "replace": [
                "relevance",  # Is replacement good?
                "role_match",  # Fills same role?
                "improvement",  # Actually better?
                "price_accuracy",  # Price delta accurate?
            ],
            "contextual": [
                "relevance",  # 0-4
                "price_accuracy",  # For upgrades/downgrades
            ],
            "similarity": [
                "similarity_score",  # 0-4
                "reasoning",  # Why similar?
            ],
        }

    def _get_user_goals(self) -> dict[str, list[str]]:
        """What users actually want (from research and design docs)."""
        return {
            "competitive": [
                "Win rate improvement",
                "Meta positioning",
                "Matchup coverage",
                "Sideboard optimization",
                "Consistency (reducing variance)",
                "**Current meta awareness** (not outdated recommendations)",
                "**Ban list awareness** (cards that are legal now)",
            ],
            "budget": [
                "Cost-effectiveness (power per dollar)",
                "Budget constraint adherence",
                "Upgrade path clarity",
                "Budget alternatives",
                "**Price stability** (not cards that just spiked)",
                "**Reprint awareness** (recent reprints = cheaper)",
            ],
            "casual": [
                "Theme consistency",
                "Fun factor",
                "Playability (not too complex)",
                "Flavor/art appeal",
            ],
            "combo": [
                "Combo piece availability",
                "Redundancy (backup pieces)",
                "Protection (counters, hexproof)",
                "Tutor targets",
            ],
            "all": [
                "Deck balance (curve, land count)",
                "Synergy awareness",
                "Format legality",
                "Card availability (printings, reprints)",
                "Power level appropriateness",
                "Explanations that help learning",
                "**Temporal context** (recommendations appropriate for their time)",
                "**Meta shift awareness** (current vs historical)",
                "**Price volatility awareness** (stable vs spiking prices)",
            ],
        }

    def analyze_missing_dimensions(self) -> list[MissingDimension]:
        """Identify what we're not judging but should be."""
        missing = []

        # 1. DECK BALANCE (Critical - we don't judge this at all)
        missing.append(
            MissingDimension(
                dimension="deck_balance",
                category="add",
                importance="critical",
                description="Does the suggestion maintain/improve deck balance? (curve, land count, color distribution)",
                why_missing="We judge individual cards but not their impact on overall deck structure",
                how_to_measure="Calculate deck stats before/after: avg CMC, land count, color distribution, compare to archetype norms",
                example_test_case="Adding 4 Lightning Bolt to a deck with 18 lands (should suggest land count adjustment)",
                current_coverage="not_judged",
            )
        )

        # 2. POWER LEVEL APPROPRIATENESS (High - implicit but not explicit)
        missing.append(
            MissingDimension(
                dimension="power_level_match",
                category="add",
                importance="high",
                description="Does the card match the deck's power level? (casual vs competitive)",
                why_missing="We judge archetype fit but not power level appropriateness",
                how_to_measure="Compare card's typical format usage (casual/competitive) to deck's intended power level",
                example_test_case="Suggesting Sol Ring to a casual kitchen table deck (power level mismatch)",
                current_coverage="implicitly_judged",  # Through archetype match, but not explicit
            )
        )

        # 3. CARD AVAILABILITY (High - we don't check this)
        missing.append(
            MissingDimension(
                dimension="card_availability",
                category="add",
                importance="high",
                description="Is the card actually available? (printings, reprints, price spikes, out of stock)",
                why_missing="We assume cards are available, but some are out of print or spiked",
                how_to_measure="Check card printings, recent price history, stock status",
                example_test_case="Suggesting a card that spiked 10x in price last week (unavailable at reasonable price)",
                current_coverage="not_judged",
            )
        )

        # 4. UPGRADE PATH CLARITY (Medium - we suggest upgrades but don't judge the path)
        missing.append(
            MissingDimension(
                dimension="upgrade_path_coherence",
                category="replace",
                importance="medium",
                description="Does the upgrade path make sense? (can you afford it? does it lead somewhere?)",
                why_missing="We suggest upgrades but don't evaluate if the path is coherent",
                how_to_measure="Check if upgrade is affordable given budget, if it leads to a coherent deck",
                example_test_case="Suggesting $50 upgrade when budget is $20 (incoherent path)",
                current_coverage="partially_judged",  # We check budget but not path coherence
            )
        )

        # 5. SYNERGY STRENGTH (High - we check existence but not strength)
        missing.append(
            MissingDimension(
                dimension="synergy_strength",
                category="contextual",
                importance="high",
                description="How strong is the synergy? (weak interaction vs combo piece)",
                why_missing="We identify synergies but don't judge their strength",
                how_to_measure="Categorize: weak (nice to have), moderate (good together), strong (synergistic), combo (essential)",
                example_test_case="Suggesting 'Goblin' card for Goblin deck (weak synergy) vs 'Goblin Chieftain' (strong synergy)",
                current_coverage="partially_judged",  # We identify synergies but don't rate strength
            )
        )

        # 6. META POSITIONING (High - competitive users care about this)
        missing.append(
            MissingDimension(
                dimension="meta_positioning",
                category="add",
                importance="high",
                description="Does this improve the deck's position in the meta? (better matchups, meta share)",
                why_missing="Competitive users care about meta, but we don't evaluate this",
                how_to_measure="Check if card improves win rate vs top decks, if it's meta-relevant",
                example_test_case="Suggesting sideboard card that improves Tron matchup (meta positioning)",
                current_coverage="not_judged",
            )
        )

        # 7. CONSISTENCY IMPROVEMENT (Medium - we don't measure variance reduction)
        missing.append(
            MissingDimension(
                dimension="consistency_improvement",
                category="add",
                importance="medium",
                description="Does this reduce deck variance? (more consistent draws, less mulligans)",
                why_missing="Competitive players value consistency, but we don't evaluate this",
                how_to_measure="Analyze deck's mana curve, card draw, filtering - does suggestion improve consistency?",
                example_test_case="Adding card draw to a deck with high variance (consistency improvement)",
                current_coverage="not_judged",
            )
        )

        # 8. LEARNING VALUE (Low - explanations help but we don't judge learning)
        missing.append(
            MissingDimension(
                dimension="explanation_learning_value",
                category="add",
                importance="low",
                description="Does the explanation help the user learn? (teaches deck building, not just 'this is good')",
                why_missing="We judge explanation quality but not learning value",
                how_to_measure="Check if explanation teaches concepts (role, synergy, meta) vs just stating facts",
                example_test_case="Explanation: 'This fills your removal gap' (learning) vs 'This is good' (not learning)",
                current_coverage="partially_judged",  # Through explanation_quality, but not explicit
            )
        )

        # 9. THEME CONSISTENCY (Medium - casual/theme decks care about this)
        missing.append(
            MissingDimension(
                dimension="theme_consistency",
                category="add",
                importance="medium",
                description="Does this maintain the deck's theme? (tribal, flavor, mechanical theme)",
                why_missing="Casual players value theme, but we only check archetype (competitive theme)",
                how_to_measure="Check if card fits theme: tribal (same creature type), flavor (same plane/set), mechanical (same mechanic)",
                example_test_case="Suggesting non-Goblin card to Goblin tribal deck (theme violation)",
                current_coverage="partially_judged",  # Through archetype, but not explicit theme
            )
        )

        # 10. REPLACEMENT ROLE OVERLAP (High - we check but don't quantify)
        missing.append(
            MissingDimension(
                dimension="replacement_role_overlap_quantified",
                category="replace",
                importance="high",
                description="How much role overlap? (0-100%, not just binary same/different)",
                why_missing="We check if roles match but don't quantify overlap percentage",
                how_to_measure="Calculate role overlap: % of functions that overlap between old and new card",
                example_test_case="Replacing Lightning Bolt with Chain Lightning (95% overlap) vs Lava Spike (60% overlap)",
                current_coverage="partially_judged",  # We check role_match but don't quantify
            )
        )

        # 11. SIDEBOARD OPTIMIZATION (High - competitive users need this)
        missing.append(
            MissingDimension(
                dimension="sideboard_optimization",
                category="add",
                importance="high",
                description="Is this a good sideboard card? (answers meta threats, flexible)",
                why_missing="We suggest maindeck cards but don't evaluate sideboard appropriateness",
                how_to_measure="Check if card answers common meta threats, if it's flexible (not narrow)",
                example_test_case="Suggesting Grafdigger's Cage for sideboard (answers graveyard decks)",
                current_coverage="not_judged",
            )
        )

        # 12. COMBO PIECE IDENTIFICATION (Medium - combo decks need this)
        missing.append(
            MissingDimension(
                dimension="combo_piece_identification",
                category="contextual",
                importance="medium",
                description="Is this a combo piece? (enables combos, protects combos, tutors for combos)",
                why_missing="Combo players need combo pieces, but we don't identify them",
                how_to_measure="Check if card is part of known combos, if it enables/protects combos",
                example_test_case="Suggesting Kiki-Jiki for Twin combo (combo piece identification)",
                current_coverage="not_judged",
            )
        )

        # 13. COST-EFFECTIVENESS (High - budget users care about this)
        missing.append(
            MissingDimension(
                dimension="cost_effectiveness",
                category="add",
                importance="high",
                description="Power per dollar - is this card worth its price? (budget efficiency)",
                why_missing="We check budget constraints but don't evaluate cost-effectiveness",
                how_to_measure="Compare card's power level to its price, compare to alternatives",
                example_test_case="Suggesting $10 card when $2 alternative is 90% as good (poor cost-effectiveness)",
                current_coverage="not_judged",
            )
        )

        # 14. FORMAT TRANSITION READINESS (Low - advanced users care)
        missing.append(
            MissingDimension(
                dimension="format_transition_readiness",
                category="add",
                importance="low",
                description="Does this help transition to a different format? (Modern → Legacy)",
                why_missing="Advanced users want format transitions, but we don't evaluate this",
                how_to_measure="Check if card is legal in target format, if it fits target format's meta",
                example_test_case="Suggesting Modern-legal card that's also Legacy-playable (transition ready)",
                current_coverage="not_judged",
            )
        )

        # 15. EXPLANATION ACTIONABILITY (Medium - we judge quality but not actionability)
        missing.append(
            MissingDimension(
                dimension="explanation_actionability",
                category="add",
                importance="medium",
                description="Can the user act on this explanation? (specific vs vague)",
                why_missing="We judge explanation quality but not whether it's actionable",
                how_to_measure="Check if explanation provides specific next steps vs vague advice",
                example_test_case="'Add 2 more lands' (actionable) vs 'Improve your mana base' (not actionable)",
                current_coverage="partially_judged",  # Through explanation_quality, but not explicit
            )
        )

        return missing

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive report of missing dimensions."""
        missing = self.analyze_missing_dimensions()

        # Group by importance
        by_importance = {
            "critical": [m for m in missing if m.importance == "critical"],
            "high": [m for m in missing if m.importance == "high"],
            "medium": [m for m in missing if m.importance == "medium"],
            "low": [m for m in missing if m.importance == "low"],
        }

        # Group by category
        by_category = {}
        for m in missing:
            if m.category not in by_category:
                by_category[m.category] = []
            by_category[m.category].append(m)

        # Group by coverage
        by_coverage = {
            "not_judged": [m for m in missing if m.current_coverage == "not_judged"],
            "partially_judged": [m for m in missing if m.current_coverage == "partially_judged"],
            "implicitly_judged": [m for m in missing if m.current_coverage == "implicitly_judged"],
        }

        return {
            "summary": {
                "total_missing": len(missing),
                "critical": len(by_importance["critical"]),
                "high": len(by_importance["high"]),
                "medium": len(by_importance["medium"]),
                "low": len(by_importance["low"]),
                "not_judged": len(by_coverage["not_judged"]),
                "partially_judged": len(by_coverage["partially_judged"]),
                "implicitly_judged": len(by_coverage["implicitly_judged"]),
            },
            "missing_dimensions": [asdict(m) for m in missing],
            "by_importance": {k: [asdict(m) for m in v] for k, v in by_importance.items()},
            "by_category": {k: [asdict(m) for m in v] for k, v in by_category.items()},
            "by_coverage": {k: [asdict(m) for m in v] for k, v in by_coverage.items()},
            "current_dimensions": self.current_dimensions,
            "user_goals": self.user_goals,
        }


def main():
    """Run missing dimensions analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze missing evaluation dimensions")
    parser.add_argument("--output", type=str, help="Output path for analysis JSON")

    args = parser.parse_args()

    analyzer = MissingDimensionsAnalyzer()
    report = analyzer.generate_report()

    # Save results
    if args.output:
        output_path = Path(args.output)
    else:
        # Import PATHS
        from pathlib import Path

        _project_root = Path(__file__).parent.parent.parent.parent
        output_path = _project_root / "experiments" / "missing_evaluation_dimensions.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print("=" * 60)
    print("Missing Evaluation Dimensions Analysis")
    print("=" * 60)
    print(f"\nTotal Missing Dimensions: {report['summary']['total_missing']}")
    print(f"  Critical: {report['summary']['critical']}")
    print(f"  High: {report['summary']['high']}")
    print(f"  Medium: {report['summary']['medium']}")
    print(f"  Low: {report['summary']['low']}")
    print("\nCoverage:")
    print(f"  Not Judged: {report['summary']['not_judged']}")
    print(f"  Partially Judged: {report['summary']['partially_judged']}")
    print(f"  Implicitly Judged: {report['summary']['implicitly_judged']}")

    print("\n" + "=" * 60)
    print("Critical Missing Dimensions")
    print("=" * 60)
    for m in report["by_importance"]["critical"]:
        print(f"\n{m['dimension']} ({m['category']}):")
        print(f"  {m['description']}")
        print(f"  Why Missing: {m['why_missing']}")
        print(f"  Example: {m['example_test_case']}")

    print("\n" + "=" * 60)
    print("High Priority Missing Dimensions")
    print("=" * 60)
    for m in report["by_importance"]["high"]:
        print(f"\n{m['dimension']} ({m['category']}):")
        print(f"  {m['description']}")

    print(f"\n✓ Results saved to {output_path}")


if __name__ == "__main__":
    main()
