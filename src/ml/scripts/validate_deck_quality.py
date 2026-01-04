#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
T0.2: Deck Quality Validation

Validates that deck completion actually works by:
1. Loading sample incomplete decks
2. Completing them using the API/system
3. Assessing quality metrics
4. Reporting success rate and quality distribution

This validates the core use case before production deployment.
"""

from __future__ import annotations

import argparse
import json
import random

# Set up project paths
import sys
from pathlib import Path
from typing import Any

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from ml.data.card_database import get_card_database
from ml.deck_building.deck_quality import assess_deck_quality
from ml.utils.logging_config import setup_script_logging
from ml.utils.paths import PATHS


try:
    from ml.enrichment.card_functional_tagger_unified import FunctionalTagger
except ImportError:
    FunctionalTagger = None

logger = setup_script_logging()


def load_sample_decks(game: str, limit: int = 50) -> list[dict[str, Any]]:
    """Load sample incomplete decks for validation."""
    decks_path = PATHS.decks_all_final

    # Fallback to game-specific deck files if final doesn't exist
    if not decks_path.exists():
        logger.warning(f"Decks file not found: {decks_path}, trying game-specific files...")
        # Try game-specific files
        game_deck_files = {
            "magic": None,  # Magic decks are typically in decks_all_final
            "pokemon": PATHS.processed / "decks_pokemon.jsonl",
            "yugioh": PATHS.processed / "decks_yugioh_ygoprodeck-tournament.jsonl",
            "riftbound": PATHS.processed / "decks_riftbound_riftmana.jsonl",
        }
        fallback_path = game_deck_files.get(game.lower())
        if fallback_path and fallback_path.exists():
            logger.info(f"Using fallback deck file: {fallback_path}")
            decks_path = fallback_path
        else:
            logger.warning(f"No fallback deck file found for {game}")
            return []

    import json

    decks = []
    try:
        with open(decks_path) as f:
            for i, line in enumerate(f):
                if i >= limit * 2:  # Load extra to account for filtering
                    break
                try:
                    deck = json.loads(line)
                    # For game-specific files, accept all decks (they're already filtered)
                    # For unified files, filter by game in source
                    is_game_specific_file = "decks_" + game.lower() in str(decks_path)
                    if (
                        is_game_specific_file
                        or game.lower() in str(deck.get("source", "")).lower()
                        or game.lower() == "magic"
                    ):
                        # Create incomplete deck (remove 10-20 random cards)
                        incomplete = create_incomplete_deck(deck, game)
                        if incomplete:
                            decks.append(incomplete)
                            if len(decks) >= limit:
                                break
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.debug(f"Skipping deck {i}: {e}")
                    continue
    except OSError as e:
        logger.error(f"Failed to read decks file {decks_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading decks: {e}")
        return []

    if not decks:
        logger.warning(f"No valid decks found for {game} in {decks_path}")

    return decks


def create_incomplete_deck(deck: dict[str, Any], game: str) -> dict[str, Any] | None:
    """Create an incomplete deck by removing some cards."""
    partition_name = "Main" if game == "magic" else ("Deck" if game == "pokemon" else "Main Deck")

    # Handle two deck formats:
    # 1. partitions array (Magic, Yu-Gi-Oh!)
    # 2. cards array with partition field (Pokemon)
    partitions = deck.get("partitions", [])
    cards_array = deck.get("cards", [])

    cards = None
    is_partitions_format = bool(partitions)

    if is_partitions_format:
        # Find main partition
        main_partition = None
        for p in partitions:
            if p.get("name") == partition_name or (
                game == "pokemon" and "Deck" in p.get("name", "")
            ):
                main_partition = p
                break

        if not main_partition:
            return None

        cards = main_partition.get("cards", [])
    else:
        # Pokemon format: cards array with partition field
        if not cards_array:
            return None
        # Filter cards by partition
        cards = [
            c
            for c in cards_array
            if c.get("partition") == partition_name
            or (game == "pokemon" and c.get("partition") == "Deck")
        ]

    if not cards or len(cards) < 20:
        return None  # Too small to be meaningful

    # Remove 10-20% of cards (but at least 5, at most 20)
    num_to_remove = max(5, min(20, len(cards) // 5))
    if num_to_remove >= len(cards):
        return None  # Can't remove all cards

    # Ensure we don't try to sample more than available
    num_to_keep = len(cards) - num_to_remove
    if num_to_keep <= 0:
        return None  # Invalid removal count

    try:
        cards_to_keep = random.sample(cards, num_to_keep)
    except ValueError:
        # Fallback if sample fails (e.g., num_to_keep > len(cards))
        cards_to_keep = cards[:num_to_keep] if num_to_keep < len(cards) else cards

    incomplete_deck = deck.copy()

    if is_partitions_format:
        incomplete_deck["partitions"] = [
            {**p, "cards": cards_to_keep}
            if (
                p.get("name") == partition_name
                or (game == "pokemon" and "Deck" in p.get("name", ""))
            )
            else p
            for p in partitions
        ]
    else:
        # Update cards array - keep cards from other partitions, update main partition cards
        other_cards = [
            c
            for c in cards_array
            if c.get("partition") != partition_name and c.get("partition") != "Deck"
        ]
        incomplete_deck["cards"] = other_cards + cards_to_keep

    return incomplete_deck


def validate_deck_completion(
    incomplete_deck: dict[str, Any],
    game: str,
    similarity_fn: Any,
    tag_set_fn: Any,
    cmc_fn: Any,
) -> dict[str, Any]:
    """Validate completion of a single deck."""
    # Check if deck_patch is available
    try:
        from ml.deck_building.deck_patch import DeckPatch, apply_deck_patch

        has_deck_patch = True
    except ImportError:
        logger.warning("deck_patch module not available - completion may be limited")
        has_deck_patch = False

    if not has_deck_patch:
        return {
            "success": False,
            "error": "deck_patch module not available",
        }

    from ml.deck_building.deck_completion import CompletionConfig, greedy_complete

    try:
        # Complete the deck using greedy completion
        config = CompletionConfig(
            game=game,
            budget_max=None,
            coverage_weight=0.5,
            max_steps=60,  # Limit steps to prevent infinite loops
        )

        # Convert Pokemon deck format to partitions if needed
        deck_to_complete = incomplete_deck
        if game == "pokemon" and "cards" in incomplete_deck and "partitions" not in incomplete_deck:
            # Convert cards array to partitions format
            # Pokemon completion expects "Main Deck" partition name
            deck_cards = [
                c for c in incomplete_deck.get("cards", []) if c.get("partition") == "Deck"
            ]
            deck_to_complete = incomplete_deck.copy()
            deck_to_complete["partitions"] = [{"name": "Main Deck", "cards": deck_cards}]
            # Keep other metadata
            for key in ["deck_id", "archetype", "format", "url", "source"]:
                if key in incomplete_deck:
                    deck_to_complete[key] = incomplete_deck[key]

        try:
            completed, steps, quality_metrics = greedy_complete(
                game=game,
                deck=deck_to_complete,
                candidate_fn=similarity_fn,
                cfg=config,
                tag_set_fn=tag_set_fn,
                assess_quality=True,
            )
        except Exception as e:
            logger.warning(f"Completion failed with exception: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Completion exception: {e!s}",
            }

        # Validate that completion actually happened
        if not completed:
            return {
                "success": False,
                "error": "Completion returned no deck",
            }
        if not steps:
            # Completion might have succeeded but no steps needed (deck already complete)
            # Check if deck size increased
            original_size = (
                sum(c.get("count", 1) for c in incomplete_deck.get("cards", []))
                if "cards" in incomplete_deck
                else sum(
                    sum(c.get("count", 1) for c in p.get("cards", []))
                    for p in incomplete_deck.get("partitions", [])
                )
            )
            completed_size = sum(
                sum(c.get("count", 1) for c in p.get("cards", []))
                for p in completed.get("partitions", [])
            )
            if completed_size <= original_size:
                return {
                    "success": False,
                    "error": f"Completion produced no steps and deck size didn't increase ({original_size} -> {completed_size})",
                }
            # If size increased but no steps, that's okay - might have been completed in one step
            logger.info(
                f"Completion succeeded without explicit steps (size: {original_size} -> {completed_size})"
            )

        # Assess quality
        try:
            quality = assess_deck_quality(
                deck=completed,
                game=game,
                tag_set_fn=tag_set_fn,
                cmc_fn=cmc_fn,
                reference_decks=None,  # Could load archetype decks
            )
        except Exception as e:
            logger.warning(f"Quality assessment failed: {e}")
            return {
                "success": True,  # Completion worked, quality assessment failed
                "quality_score": None,
                "error": f"Quality assessment failed: {e}",
                "num_steps": len(steps),
            }

        return {
            "success": True,
            "quality_score": quality.overall_score,
            "mana_curve_score": quality.mana_curve_score,
            "tag_balance_score": quality.tag_balance_score,
            "synergy_score": quality.synergy_score,
            "num_cards": quality.num_cards,
            "num_unique_tags": quality.num_unique_tags,
            "num_steps": len(steps),
        }
    except Exception as e:
        logger.warning(f"Deck completion failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


def validate_deck_quality_batch(
    game: str = "magic",
    num_decks: int = 50,
    quality_threshold: float = 6.0,
) -> dict[str, Any]:
    """Validate deck completion quality on a batch of decks."""
    logger.info(f"Validating deck quality for {game} ({num_decks} decks)")

    # Load assets with error handling
    try:
        from ml.scripts.evaluate_downstream_complete import load_trained_assets

        assets = load_trained_assets(
            game=game,
            fast_mode=True,  # Skip expensive components
        )
    except Exception as e:
        logger.error(f"Failed to load trained assets: {e}")
        return {"error": f"Failed to load trained assets: {e}"}

    if not assets.get("fusion"):
        logger.error("Failed to load fusion system")
        return {"error": "Failed to load fusion system"}

    # Load functional tagger with fallback
    try:
        tagger = FunctionalTagger()
        tag_set_fn = lambda card: set(tagger.tag_card(card).keys())
    except Exception as e:
        logger.warning(f"Functional tagger not available: {e}, using empty tags")
        tag_set_fn = lambda card: set()

    # Load CMC function with error handling
    try:
        card_db = get_card_database()

        def cmc_fn(card: str) -> int | None:
            try:
                data = card_db.get_card_data(card, game=game)
                if data and "cmc" in data:
                    try:
                        return int(data["cmc"])
                    except (ValueError, TypeError):
                        return None
                return None
            except Exception:
                return None
    except Exception as e:
        logger.warning(f"Card database not available: {e}, using None for CMC")
        cmc_fn = lambda card: None

    # Create similarity function
    def similarity_fn(query: str, k: int = 10) -> list[tuple[str, float]]:
        try:
            return assets["fusion"].similar(query, k=k)
        except Exception as e:
            logger.warning(f"Similarity lookup failed for {query}: {e}")
            return []

    # Load sample decks
    sample_decks = load_sample_decks(game, limit=num_decks)
    if not sample_decks:
        logger.error("No sample decks found")
        return {"error": "No sample decks found"}

    logger.info(f"Loaded {len(sample_decks)} sample decks")

    # Validate each deck with progress reporting
    results = []
    for i, deck in enumerate(sample_decks, 1):
        logger.info(f"[{i}/{len(sample_decks)}] Validating deck...")
        try:
            result = validate_deck_completion(
                incomplete_deck=deck,
                game=game,
                similarity_fn=similarity_fn,
                tag_set_fn=tag_set_fn,
                cmc_fn=cmc_fn,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Unexpected error validating deck {i}: {e}", exc_info=True)
            results.append(
                {
                    "success": False,
                    "error": f"Unexpected error: {e}",
                }
            )

    # Compute statistics with error handling
    successful = [r for r in results if r.get("success")]
    if not results:
        return {"error": "No validation results generated"}

    # Safe division for success rate
    from ml.scripts.fix_nuances import safe_division

    success_rate = safe_division(len(successful), len(results), default=0.0, name="success_rate")

    quality_scores = [
        r["quality_score"]
        for r in successful
        if "quality_score" in r and r["quality_score"] is not None
    ]
    if not quality_scores:
        logger.warning("No quality scores available - completion may have failed")
        avg_quality = 0.0
        above_threshold = 0
        threshold_rate = 0.0
    else:
        # Safe division for averages
        avg_quality = safe_division(
            sum(quality_scores), len(quality_scores), default=0.0, name="avg_quality"
        )
        above_threshold = sum(1 for q in quality_scores if q >= quality_threshold)
        threshold_rate = safe_division(
            above_threshold, len(quality_scores), default=0.0, name="threshold_rate"
        )

    return {
        "game": game,
        "num_decks_tested": len(results),
        "num_successful": len(successful),
        "success_rate": success_rate,
        "avg_quality_score": avg_quality,
        "quality_threshold": quality_threshold,
        "above_threshold_rate": threshold_rate,
        "quality_distribution": {
            "min": min(quality_scores) if quality_scores else 0.0,
            "max": max(quality_scores) if quality_scores else 0.0,
            "mean": avg_quality,
            "median": sorted(quality_scores)[len(quality_scores) // 2] if quality_scores else 0.0,
        },
        "results": results,
    }


def main() -> int:
    """CLI for deck quality validation."""
    parser = argparse.ArgumentParser(description="Validate deck completion quality")
    parser.add_argument(
        "--game",
        type=str,
        default="magic",
        choices=["magic", "pokemon", "yugioh"],
        help="Game to validate",
    )
    parser.add_argument(
        "--num-decks",
        type=int,
        default=50,
        help="Number of decks to test",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=6.0,
        help="Quality score threshold (0-10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "deck_quality_validation.json",
        help="Output JSON file",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()

    # Set random seed for reproducibility
    random.seed(args.seed)
    logger.info(f"Using random seed: {args.seed}")

    try:
        results = validate_deck_quality_batch(
            game=args.game,
            num_decks=args.num_decks,
            quality_threshold=args.quality_threshold,
        )
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}", exc_info=True)
        return 1

    if "error" in results:
        logger.error(f"Validation failed: {results['error']}")
        return 1

    # Save results with error handling
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        return 1

    # Print summary
    print("\n" + "=" * 70)
    print("Deck Quality Validation Results")
    print("=" * 70)
    print(f"Game: {results['game']}")
    print(f"Decks tested: {results['num_decks_tested']}")
    print(f"Success rate: {results['success_rate']:.1%}")
    if results.get("avg_quality_score", 0) > 0:
        print(f"Average quality: {results['avg_quality_score']:.2f}/10.0")
        print(
            f"Above threshold ({results['quality_threshold']}): {results['above_threshold_rate']:.1%}"
        )
    else:
        print("Warning: No quality scores available")
    print(f"\nResults saved to: {args.output}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
