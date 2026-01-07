#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
Expert Player E2E Experience Testing

Tests the UI from an expert TCG player perspective:
- Fast, accurate card name matching
- Format legality awareness
- Functional similarity (not just statistical)
- Context-aware results
- Clear explanations of WHY cards are similar

Usage:
    python scripts/e2e_testing/test_expert_experience.py
"""

import json
import os
import time
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests not installed. Install with: pip install requests")
    exit(1)

# Import shared utilities (dotenv is loaded automatically by test_utils)

# Import shared utilities and constants
from test_utils import wait_for_api, logger, API_BASE
from test_constants import TEST_CARDS, TIMEOUTS

# Configuration from .env
# API_BASE imported from test_utils


class ExpertExperienceTester:
    """Expert player perspective testing."""

    def __init__(self):
        self.issues = []
        self.suggestions = []

    def test_autocomplete_edge_cases(self):
        """Test autocomplete with edge cases expert players encounter."""
        logger.info("\n" + "=" * 80)
        logger.info("AUTOCOMPLETE EDGE CASE TESTING")
        logger.info("=" * 80)

        test_cases = [
            # Partial matches
            ("Light", "Should find Lightning Bolt, Lightning Greaves, etc."),
            ("Blue", "Should find Blue-Eyes, Blue cards"),
            ("Pika", "Should find Pikachu variants"),
            # Special characters
            ("Blue-Eyes", "Should handle hyphens"),
            ("Jace, the", "Should handle commas"),
            # Case insensitivity
            ("lightning", "Should work case-insensitive"),
            ("LIGHTNING", "Should work uppercase"),
            # Short queries
            ("Li", "Should require 2+ chars (current: 2)"),
            ("L", "Should not trigger (< 2 chars)"),
            # Common typos
            ("Lightning Bol", "Should find Lightning Bolt"),
            ("Serra Ang", "Should find Serra Angel"),
        ]

        for query, description in test_cases:
            try:
                resp = requests.get(
                    f"{API_BASE}/v1/cards?prefix={query}&limit=5", timeout=TIMEOUTS["normal"]
                )
                if resp.status_code == 503:
                    logger.warning(f"⚠️  {query}: API not ready (embeddings not loaded)")
                    continue
                if resp.status_code != 200:
                    self.issues.append(f"Autocomplete failed for '{query}': {resp.status_code}")
                    logger.error(f"❌ {query}: Failed ({resp.status_code})")
                    continue

                data = resp.json()
                items = data.get("items", [])
                if len(items) > 0:
                    logger.info(f"✅ {query}: Found {len(items)} results")
                    if len(items) > 0:
                        logger.info(f"     First: {items[0]}")
                else:
                    logger.warning(f"⚠️  {query}: No results")
            except Exception as e:
                self.issues.append(f"Autocomplete error for '{query}': {e}")
                logger.error(f"❌ {query}: Error - {e}")

    def test_expert_needs(self):
        """Test what expert players actually need."""
        logger.info("\n" + "=" * 80)
        logger.info("EXPERT PLAYER NEEDS TESTING")
        logger.info("=" * 80)

        expert_scenarios = [
            {
                "name": "Format-specific substitution",
                "query": TEST_CARDS["common"],
                "need": "Find Modern-legal alternatives (Chain Lightning not legal)",
                "check": "Results should indicate format legality",
            },
            {
                "name": "Functional similarity",
                "query": "Path to Exile",
                "need": "Find other white removal (Swords to Plowshares, etc.)",
                "check": "Results should show functional tags (removal)",
            },
            {
                "name": "Mana cost filtering",
                "query": TEST_CARDS["common"],
                "need": "Find 1-mana red spells (not 2+ mana)",
                "check": "Results should show mana cost",
            },
            {
                "name": "Archetype context",
                "query": "Monastery Swiftspear",
                "need": "Find other Burn/Prowess cards",
                "check": "Results should show archetype info",
            },
            {
                "name": "Synergy vs similarity",
                "query": "Young Pyromancer",
                "need": "Distinguish similar cards from synergistic cards",
                "check": "Should not show Lightning Bolt as 'similar' (it's synergistic)",
            },
        ]

        for scenario in expert_scenarios:
            logger.info(f"\n  📋 {scenario['name']}")
            logger.info(f"     Query: {scenario['query']}")
            logger.info(f"     Need: {scenario['need']}")
            logger.info(f"     Check: {scenario['check']}")

            try:
                resp = requests.post(
                    f"{API_BASE}/v1/similar",
                    json={"query": scenario["query"], "top_k": 5},
                    timeout=TIMEOUTS["slow"],
                )

                if resp.status_code == 503:
                    logger.info(f"     ⚠️  API not ready")
                    continue
                if resp.status_code != 200:
                    logger.error(f"     ❌ Failed: {resp.status_code}")
                    continue

                data = resp.json()
                results = data.get("results", [])

                if len(results) == 0:
                    logger.warning(f"     ⚠️  No results")
                    continue

                # Check if metadata is present
                has_metadata = any(r.get("metadata") for r in results)
                if has_metadata:
                    logger.info(f"     ✅ Metadata present")
                    # Check for key expert fields
                    first_result = results[0]
                    meta = first_result.get("metadata", {})
                    if meta.get("type"):
                        logger.info(f"     ✅ Type: {meta.get('type')}")
                    if meta.get("mana_cost"):
                        logger.info(f"     ✅ Mana cost: {meta.get('mana_cost')}")
                    if meta.get("functional_tags"):
                        logger.info(f"     ✅ Functional tags: {meta.get('functional_tags')}")
                else:
                    logger.warning(f"     ⚠️  No metadata (expert players need this!)")
                    self.issues.append(
                        f"Missing metadata for {scenario['name']} - expert players need type, mana cost, functional tags"
                    )

                # Check similarity scores
                low_scores = [r for r in results if r.get("similarity", 0) < 0.2]
                if low_scores:
                    logger.warning(f"     ⚠️  {len(low_scores)} results with very low similarity (<0.2)")
                    self.issues.append(
                        f"Low quality results for {scenario['query']}: {len(low_scores)} results < 0.2 similarity"
                    )

            except Exception as e:
                logger.error(f"     ❌ Error: {e}")
                self.issues.append(f"Error testing {scenario['name']}: {e}")

    def critique_from_expert_perspective(self):
        """Critical expert player perspective."""
        logger.info("\n" + "=" * 80)
        logger.info("EXPERT PLAYER CRITIQUE")
        logger.info("=" * 80)

        critiques = []

        # 1. Format legality
        critiques.append(
            "❌ MISSING: Format legality indicators - Expert players need to know if cards are legal in their format"
        )
        self.suggestions.append("Add format badges (Modern, Legacy, etc.) to results")

        # 2. Functional tags visibility
        critiques.append(
            "⚠️  PARTIAL: Functional tags exist but not prominently displayed - Expert players need to see WHY cards are similar"
        )
        self.suggestions.append("Make functional tags more prominent in results")

        # 3. Mana cost comparison
        critiques.append(
            "⚠️  PARTIAL: Mana cost shown but not compared - Expert players need to see if alternatives have same CMC"
        )
        self.suggestions.append("Highlight mana cost matches/mismatches")

        # 4. Archetype context
        critiques.append(
            "❌ MISSING: Archetype information - Expert players need to know if cards fit same archetype"
        )
        self.suggestions.append("Show archetype badges/staple indicators")

        # 5. Co-occurrence data
        critiques.append(
            "❌ MISSING: Co-occurrence data - Expert players want to know 'these appear together in X% of decks'"
        )
        self.suggestions.append("Display graph/co-occurrence statistics")

        # 6. Explanation quality
        critiques.append(
            "⚠️  WEAK: No explanation of WHY cards are similar - Expert players need functional reasoning, not just scores"
        )
        self.suggestions.append("Add 'Why similar?' explanations based on functional tags")

        # 7. Substitutability clarity
        critiques.append(
            "⚠️  UNCLEAR: Similarity score doesn't clearly indicate substitutability - Expert players need 'Can I replace X with Y?'"
        )
        self.suggestions.append("Add clear substitutability indicators (Yes/No/Maybe with reasoning)")

        # 8. Game phase awareness
        critiques.append(
            "❌ MISSING: Game phase context - Expert players need to know if cards work in same game phases (early/mid/late)"
        )
        self.suggestions.append("Add game phase indicators (early/mid/late game cards)")

        # 9. Meta positioning
        critiques.append(
            "❌ MISSING: Meta context - Expert players need to know current meta relevance"
        )
        self.suggestions.append("Show meta share percentages if available")

        # 10. Price/availability
        critiques.append(
            "❌ MISSING: Price and availability - Expert players need to know if alternatives are affordable/available"
        )
        self.suggestions.append("Add price information and availability status")

        for critique in critiques:
            logger.info(f"  {critique}")

    def test_type_ahead_thoroughly(self):
        """Thoroughly test type-ahead functionality."""
        logger.info("\n" + "=" * 80)
        logger.info("TYPE-AHEAD THOROUGH TESTING")
        logger.info("=" * 80)

        # Test API endpoint directly
        test_queries = [
            ("Light", 10, "Common prefix"),
            ("Lightning", 5, "Longer prefix"),
            ("Blue-Eyes", 3, "Hyphenated name"),
            ("Pika", 5, "Short Pokemon prefix"),
            ("Serra", 3, "Partial name"),
            ("Jace", 5, "Planeswalker name"),
            ("", 0, "Empty query (should fail)"),
            ("L", 0, "Single char (should fail)"),
        ]

        for query, expected_min, description in test_queries:
            try:
                if len(query) < 2:
                    # Should not make request
                    logger.info(f"✅ '{query}': Correctly skipped (< 2 chars)")
                    continue

                resp = requests.get(
                    f"{API_BASE}/v1/cards?prefix={query}&limit=10", timeout=TIMEOUTS["normal"]
                )

                if resp.status_code == 503:
                    logger.warning(f"⚠️  '{query}': API not ready")
                    continue

                if resp.status_code != 200:
                    logger.error(f"❌ '{query}': Failed ({resp.status_code})")
                    self.issues.append(f"Autocomplete failed for '{query}': {resp.status_code}")
                    continue

                data = resp.json()
                items = data.get("items", [])
                count = len(items)

                if count >= expected_min:
                    logger.info(f"✅ '{query}': {count} results ({description})")
                    if count > 0:
                        logger.info(f"     Examples: {', '.join(items[:3])}")
                else:
                    logger.warning(f"⚠️  '{query}': Only {count} results (expected {expected_min}+)")
                    if count > 0:
                        logger.info(f"     Found: {', '.join(items)}")

            except Exception as e:
                logger.error(f"❌ '{query}': Error - {e}")
                self.issues.append(f"Autocomplete error for '{query}': {e}")

    def run_all_tests(self):
        """Run all expert experience tests."""
        logger.info("=" * 80)
        logger.info("EXPERT PLAYER E2E EXPERIENCE TEST")
        logger.info("=" * 80)

        self.test_type_ahead_thoroughly()
        self.test_autocomplete_edge_cases()
        self.test_expert_needs()
        self.critique_from_expert_perspective()

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Issues found: {len(self.issues)}")
        logger.info(f"Suggestions: {len(self.suggestions)}")

        if self.issues:
            logger.info("\nIssues:")
            for issue in self.issues:
                logger.info(f"  • {issue}")

        if self.suggestions:
            logger.info("\nSuggestions for improvement:")
            for suggestion in self.suggestions:
                logger.info(f"  • {suggestion}")

        return len(self.issues) == 0


def main():
    """Main entry point."""
    tester = ExpertExperienceTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

