#!/usr/bin/env python3
"""
Analyze visual embedding coverage across games.

Reports % of cards with image URLs, identifies gaps, and prioritizes collection.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths
    setup_project_paths()
except ImportError:
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

import argparse
import json
import logging
from collections import defaultdict
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_image_coverage(
    card_data_path: Path | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Analyze image URL coverage in card data."""
    logger.info("Analyzing visual embedding coverage...")
    
    # Try to load card data from various sources
    card_data = {}
    
    if card_data_path and card_data_path.exists():
        logger.info(f"Loading card data from {card_data_path}")
        if card_data_path.suffix == ".json":
            with open(card_data_path) as f:
                data = json.load(f)
                if isinstance(data, list):
                    card_data = {card.get("name", ""): card for card in data if card.get("name")}
                elif isinstance(data, dict):
                    card_data = data
        elif card_data_path.suffix == ".csv":
            import pandas as pd
            df = pd.read_csv(card_data_path)
            for _, row in df.iterrows():
                name = str(row.get("name", ""))
                if name:
                    card_data[name] = row.to_dict()
    
    if not card_data:
        logger.warning("No card data loaded. Provide --card-data path or ensure data exists.")
        return {
            "total_cards": 0,
            "cards_with_images": 0,
            "coverage_percent": 0.0,
            "missing_images": [],
        }
    
    # Analyze image URLs
    from ml.similarity.visual_embeddings import CardVisualEmbedder
    
    embedder = CardVisualEmbedder()
    
    cards_with_images = 0
    missing_images = []
    
    for card_name, card_dict in card_data.items():
        image_url = embedder._get_image_url(card_dict if isinstance(card_dict, dict) else {"name": card_name})
        if image_url:
            cards_with_images += 1
        else:
            missing_images.append(card_name)
    
    coverage_percent = (cards_with_images / len(card_data) * 100) if card_data else 0.0
    
    logger.info(f"  Total cards: {len(card_data)}")
    logger.info(f"  Cards with images: {cards_with_images}")
    logger.info(f"  Coverage: {coverage_percent:.1f}%")
    logger.info(f"  Missing images: {len(missing_images)}")
    
    return {
        "total_cards": len(card_data),
        "cards_with_images": cards_with_images,
        "coverage_percent": coverage_percent,
        "missing_images": missing_images[:100],  # Limit to first 100
    }


def analyze_by_game() -> dict[str, Any]:
    """Analyze coverage across different games."""
    logger.info("Analyzing coverage by game...")
    
    results = {}
    
    # Try to find card data for each game
    games = ["magic", "pokemon", "yugioh", "riftbound"]
    
    for game in games:
        logger.info(f"\nAnalyzing {game}...")
        # Try to find card data
        possible_paths = [
            Path(f"data/{game}_cards.json"),
            Path(f"data/processed/{game}_cards.json"),
            Path(f"data/raw/{game}_cards.json"),
        ]
        
        card_data_path = None
        for path in possible_paths:
            if path.exists():
                card_data_path = path
                break
        
        if card_data_path:
            results[game] = analyze_image_coverage(card_data_path=card_data_path, game=game)
        else:
            logger.warning(f"  No card data found for {game}")
            results[game] = {"error": "No card data found"}
    
    return results


def main() -> int:
    """Main coverage analysis script."""
    parser = argparse.ArgumentParser(
        description="Analyze visual embedding coverage across games"
    )
    parser.add_argument(
        "--card-data",
        type=Path,
        help="Path to card data JSON/CSV file",
    )
    parser.add_argument(
        "--game",
        type=str,
        choices=["magic", "pokemon", "yugioh", "riftbound"],
        help="Game to analyze (if not provided, analyzes all games)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to save coverage analysis JSON",
    )
    parser.add_argument(
        "--all-games",
        action="store_true",
        help="Analyze all games",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Visual Embedding Coverage Analysis")
    logger.info("=" * 60)
    logger.info("")
    
    if args.all_games or not args.game:
        # Analyze all games
        results = analyze_by_game()
    else:
        # Analyze single game
        if args.card_data:
            results = {args.game: analyze_image_coverage(card_data_path=args.card_data, game=args.game)}
        else:
            logger.warning("--card-data required when analyzing single game")
            return 1
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Coverage Summary")
    logger.info("=" * 60)
    logger.info("")
    logger.info(f"{'Game':<15} {'Total Cards':<15} {'With Images':<15} {'Coverage':<15}")
    logger.info("-" * 60)
    
    for game, result in results.items():
        if "error" not in result:
            total = result.get("total_cards", 0)
            with_images = result.get("cards_with_images", 0)
            coverage = result.get("coverage_percent", 0.0)
            logger.info(f"{game:<15} {total:<15} {with_images:<15} {coverage:<15.1f}%")
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\nResults saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

