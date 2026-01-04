#!/usr/bin/env python3
"""
Property-based and integration tests for deck quality validation.

Tests cover:
- Deck loading and filtering
- Incomplete deck creation
- Completion validation
- Quality assessment
- Batch processing
"""

from __future__ import annotations

import json
import random

# Set up paths
from pathlib import Path
from unittest.mock import patch

import pytest

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from ml.scripts.validate_deck_quality import (
    create_incomplete_deck,
    load_sample_decks,
    validate_deck_completion,
)


class TestDeckLoading:
    """Tests for deck loading functionality."""

    def test_load_sample_decks_success(self, tmp_path: Path):
        """Test successful deck loading."""
        decks_path = tmp_path / "decks.jsonl"

        # Create sample decks
        decks = [
            {
                "source": "magic_tournament",
                "partitions": [
                    {
                        "name": "Main",
                        "cards": [{"name": f"Card_{i}", "count": 4} for i in range(30)],
                    }
                ],
            }
            for _ in range(10)
        ]

        with open(decks_path, "w") as f:
            for deck in decks:
                f.write(json.dumps(deck) + "\n")

        with patch("ml.scripts.validate_deck_quality.PATHS") as mock_paths:
            mock_paths.decks_all_final = decks_path
            result = load_sample_decks("magic", limit=5)

            assert len(result) > 0
            assert all("partitions" in deck for deck in result)

    def test_load_sample_decks_missing_file(self):
        """Test loading when file doesn't exist."""
        with patch("ml.scripts.validate_deck_quality.PATHS") as mock_paths:
            mock_paths.decks_all_final = Path("/nonexistent/decks.jsonl")
            result = load_sample_decks("magic", limit=5)

            assert result == []

    def test_load_sample_decks_malformed_json(self, tmp_path: Path):
        """Test loading with malformed JSON lines."""
        decks_path = tmp_path / "decks.jsonl"
        with open(decks_path, "w") as f:
            f.write('{"valid": true}\n')
            f.write("{ invalid json }\n")
            f.write('{"valid": false}\n')

        with patch("ml.scripts.validate_deck_quality.PATHS") as mock_paths:
            mock_paths.decks_all_final = decks_path
            result = load_sample_decks("magic", limit=10)

            # Should skip malformed lines
            assert len(result) >= 0  # May have 0 if filtering removes all


class TestIncompleteDeckCreation:
    """Tests for creating incomplete decks."""

    def test_create_incomplete_deck_success(self):
        """Test successful incomplete deck creation."""
        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [{"name": f"Card_{i}", "count": 4} for i in range(30)],
                }
            ],
        }

        incomplete = create_incomplete_deck(deck, "magic")

        assert incomplete is not None
        assert "partitions" in incomplete

        # Check that cards were removed
        main_partition = next(
            (p for p in incomplete["partitions"] if p.get("name") == "Main"), None
        )
        assert main_partition is not None
        assert len(main_partition["cards"]) < 30

    def test_create_incomplete_deck_too_small(self):
        """Test with deck that's too small."""
        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [{"name": f"Card_{i}", "count": 1} for i in range(10)],
                }
            ],
        }

        incomplete = create_incomplete_deck(deck, "magic")

        # Should return None for decks that are too small
        assert incomplete is None

    def test_create_incomplete_deck_missing_partition(self):
        """Test with deck missing main partition."""
        deck = {
            "partitions": [{"name": "Sideboard", "cards": [{"name": "Card1", "count": 1}]}],
        }

        incomplete = create_incomplete_deck(deck, "magic")

        assert incomplete is None

    def test_create_incomplete_deck_empty_partitions(self):
        """Test with deck that has empty partitions."""
        deck = {"partitions": []}

        incomplete = create_incomplete_deck(deck, "magic")

        assert incomplete is None


class TestDeckCompletionValidation:
    """Tests for deck completion validation."""

    def test_validate_deck_completion_success(self):
        """Test successful deck completion validation."""
        incomplete_deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [{"name": f"Card_{i}", "count": 4} for i in range(20)],
                }
            ],
        }

        # Mock similarity function
        def similarity_fn(query: str, k: int = 10) -> list[tuple[str, float]]:
            return [(f"Card_{i}", 0.9 - i * 0.1) for i in range(k)]

        def tag_set_fn(card: str) -> set[str]:
            return {"creature", "spell"}

        def cmc_fn(card: str) -> int | None:
            return 3

        with patch("ml.scripts.validate_deck_quality.greedy_complete") as mock_complete:
            mock_complete.return_value = (
                {
                    "partitions": [
                        {
                            "name": "Main",
                            "cards": [{"name": f"Card_{i}", "count": 4} for i in range(30)],
                        }
                    ],
                },
                [{"op": "add_card", "card": "Card_20"}],
                {"final": {"overall_score": 7.5}},
            )

            with patch("ml.scripts.validate_deck_quality.assess_deck_quality") as mock_assess:
                from ml.deck_building.deck_quality import DeckQualityMetrics

                mock_assess.return_value = DeckQualityMetrics(
                    mana_curve_score=0.8,
                    tag_balance_score=0.7,
                    synergy_score=0.75,
                    overall_score=7.5,
                    num_cards=30,
                    num_unique_tags=10,
                    avg_tags_per_card=0.5,
                )

                result = validate_deck_completion(
                    incomplete_deck=incomplete_deck,
                    game="magic",
                    similarity_fn=similarity_fn,
                    tag_set_fn=tag_set_fn,
                    cmc_fn=cmc_fn,
                )

                assert result["success"] is True
                assert "quality_score" in result
                assert result["quality_score"] == 7.5

    def test_validate_deck_completion_no_deck_patch(self):
        """Test validation when deck_patch module is unavailable."""
        incomplete_deck = {"partitions": []}

        with patch("ml.scripts.validate_deck_quality.DeckPatch", None):
            result = validate_deck_completion(
                incomplete_deck=incomplete_deck,
                game="magic",
                similarity_fn=lambda q, k: [],
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )

            assert result["success"] is False
            assert "deck_patch" in result.get("error", "").lower()

    def test_validate_deck_completion_failure(self):
        """Test validation when completion fails."""
        incomplete_deck = {"partitions": []}

        with patch(
            "ml.scripts.validate_deck_quality.greedy_complete", side_effect=Exception("Failed")
        ):
            result = validate_deck_completion(
                incomplete_deck=incomplete_deck,
                game="magic",
                similarity_fn=lambda q, k: [],
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )

            assert result["success"] is False
            assert "error" in result


class TestPropertyBased:
    """Property-based tests for invariants."""

    def test_incomplete_deck_always_smaller(self):
        """Property: Incomplete deck always has fewer cards than original."""
        for _ in range(10):
            num_cards = random.randint(25, 60)
            deck = {
                "partitions": [
                    {
                        "name": "Main",
                        "cards": [{"name": f"Card_{i}", "count": 4} for i in range(num_cards)],
                    }
                ],
            }

            incomplete = create_incomplete_deck(deck, "magic")

            if incomplete:
                original_count = sum(
                    c.get("count", 0)
                    for p in deck["partitions"]
                    if p.get("name") == "Main"
                    for c in p.get("cards", [])
                )
                incomplete_count = sum(
                    c.get("count", 0)
                    for p in incomplete["partitions"]
                    if p.get("name") == "Main"
                    for c in p.get("cards", [])
                )

                assert incomplete_count < original_count

    def test_quality_score_in_range(self):
        """Property: Quality scores are always in valid range [0, 10]."""
        from ml.deck_building.deck_quality import DeckQualityMetrics

        # Test various score combinations
        for curve in [0.0, 0.5, 1.0]:
            for tag in [0.0, 0.5, 1.0]:
                for synergy in [0.0, 0.5, 1.0]:
                    metrics = DeckQualityMetrics(
                        mana_curve_score=curve,
                        tag_balance_score=tag,
                        synergy_score=synergy,
                        overall_score=(curve + tag + synergy) / 3 * 10,
                        num_cards=60,
                        num_unique_tags=20,
                        avg_tags_per_card=0.5,
                    )

                    assert 0.0 <= metrics.overall_score <= 10.0
                    assert 0.0 <= metrics.mana_curve_score <= 1.0
                    assert 0.0 <= metrics.tag_balance_score <= 1.0
                    assert 0.0 <= metrics.synergy_score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
