#!/usr/bin/env python3
"""
Post-Update Quality Fix Pipeline

Runs quality checks and fixes after graph updates to ensure data integrity.
Integrates with the incremental update pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def run_post_update_fixes(
    graph_db: Path,
    fix_unknown: bool = True,
    fix_mismatches: bool = True,
    fix_cross_game: bool = True,
    api_fallback: bool = False,
    min_decks_for_api: int = 100,
) -> dict[str, int]:
    """
    Run quality fixes after graph update.
    
    Args:
        graph_db: Path to graph database
        fix_unknown: Fix unknown nodes
        fix_mismatches: Fix mismatched edges
        fix_cross_game: Fix cross-game edges
        api_fallback: Use API fallback for unknown nodes
        min_decks_for_api: Minimum deck count for API fallback
        
    Returns:
        Dictionary with fix results
    """
    results = {}
    
    logger.info("=" * 70)
    logger.info("Post-Update Quality Fixes")
    logger.info("=" * 70)
    
    # 1. Fix multilingual card names for ALL games
    if fix_unknown:
        logger.info("\n1. Fixing multilingual card names for all games...")
        try:
            # Try comprehensive multilingual API fix (all languages, all games)
            try:
                from .fix_all_games_multilingual import fix_all_games_multilingual
                all_games_results = fix_all_games_multilingual(
                    graph_db, min_decks=min_decks_for_api, limit=100
                )
                results["multilingual_all_games"] = all_games_results
                # Extract Magic results for backward compatibility
                if "magic" in all_games_results:
                    magic_results = all_games_results["magic"]
                    results["multilingual_fixed"] = magic_results.get("fixed", 0)
                    results["multilingual_by_lang"] = magic_results.get("by_language", {})
            except Exception as e:
                logger.debug(f"All-games multilingual fix not available, trying Magic only: {e}")
                # Fallback to Magic-only fix
                try:
                    from .fix_multilingual_cards_with_api import fix_multilingual_cards_with_api
                    multilingual_results = fix_multilingual_cards_with_api(
                        graph_db, min_decks=min_decks_for_api, limit=100
                    )
                    results["multilingual_fixed"] = multilingual_results.get("fixed", 0)
                    results["multilingual_by_lang"] = multilingual_results.get("by_language", {})
                except Exception as e2:
                    logger.debug(f"Multilingual API fix not available: {e2}")
                    results["multilingual_fixed"] = 0
            
            # Fallback to Spanish-specific fixes
            try:
                from .fix_spanish_cards_with_scryfall import fix_spanish_cards_with_scryfall
                scryfall_results = fix_spanish_cards_with_scryfall(
                    graph_db, min_decks=min_decks_for_api, limit=50
                )
                results["spanish_fixed_scryfall"] = scryfall_results.get("fixed", 0)
            except Exception as e:
                logger.debug(f"Scryfall API fix not available: {e}")
                results["spanish_fixed_scryfall"] = 0
            
            # Fallback to dictionary-based translation
            try:
                from .fix_spanish_card_names import fix_spanish_card_names
                spanish_results = fix_spanish_card_names(graph_db, min_decks=min_decks_for_api)
                results["spanish_fixed"] = spanish_results.get("fixed", 0)
            except Exception as e:
                logger.warning(f"Could not fix Spanish card names: {e}")
                results["spanish_fixed"] = 0
        except Exception as e:
            logger.warning(f"Could not fix multilingual card names: {e}")
            results["multilingual_fixed"] = 0
    
    # 2. Fix unknown nodes (with optional API fallback)
    if fix_unknown:
        logger.info("\n2. Fixing remaining unknown nodes...")
        try:
            if api_fallback:
                from .fix_unknown_nodes_with_api import fix_unknown_nodes_with_api
                api_results = fix_unknown_nodes_with_api(
                    graph_db, min_decks=min_decks_for_api, limit=100
                )
                results["unknown_fixed_api"] = api_results.get("fixed", 0)
            else:
                from .fix_all_remaining_issues import fix_unknown_nodes_aggressive
                fix_results = fix_unknown_nodes_aggressive(graph_db)
                results["unknown_fixed"] = fix_results.get("fixed", 0)
        except Exception as e:
            logger.warning(f"Could not fix unknown nodes: {e}")
            results["unknown_fixed"] = 0
    
    # 3. Fix mismatched edges
    if fix_mismatches:
        logger.info("\n3. Fixing mismatched edges...")
        try:
            from .fix_mismatched_edges_smart import fix_mismatched_edges_smart
            mismatch_results = fix_mismatched_edges_smart(graph_db)
            results["edges_fixed"] = mismatch_results.get("fixed_edges", 0)
            results["nodes_fixed"] = mismatch_results.get("fixed_nodes", 0)
        except Exception as e:
            logger.warning(f"Could not fix mismatched edges: {e}")
            results["edges_fixed"] = 0
            results["nodes_fixed"] = 0
    
    # 4. Fix cross-game edges
    if fix_cross_game:
        logger.info("\n4. Fixing cross-game edges...")
        try:
            from .fix_cross_game_edges import fix_cross_game_edges
            cross_game_results = fix_cross_game_edges(graph_db)
            results["cross_game_fixed"] = cross_game_results.get("fixed", 0)
        except Exception as e:
            logger.warning(f"Could not fix cross-game edges: {e}")
            results["cross_game_fixed"] = 0
    
    logger.info("\n" + "=" * 70)
    logger.info("Post-Update Fixes Complete")
    logger.info("=" * 70)
    for key, value in results.items():
        logger.info(f"  {key}: {value:,}")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run quality fixes after graph update")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--skip-unknown",
        action="store_true",
        help="Skip fixing unknown nodes",
    )
    parser.add_argument(
        "--skip-mismatches",
        action="store_true",
        help="Skip fixing mismatched edges",
    )
    parser.add_argument(
        "--skip-cross-game",
        action="store_true",
        help="Skip fixing cross-game edges",
    )
    parser.add_argument(
        "--api-fallback",
        action="store_true",
        help="Use API fallback for high-frequency unknown cards",
    )
    parser.add_argument(
        "--min-decks-for-api",
        type=int,
        default=100,
        help="Minimum deck count for API fallback (default: 100)",
    )
    
    args = parser.parse_args()
    
    results = run_post_update_fixes(
        graph_db=args.graph_db,
        fix_unknown=not args.skip_unknown,
        fix_mismatches=not args.skip_mismatches,
        fix_cross_game=not args.skip_cross_game,
        api_fallback=args.api_fallback,
        min_decks_for_api=args.min_decks_for_api,
    )
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

