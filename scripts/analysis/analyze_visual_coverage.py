#!/usr/bin/env python3
"""
Analyze visual embedding coverage across the dataset.

Reports coverage statistics and identifies cards missing images.
"""

import json
import sys
from pathlib import Path
from typing import Any

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

import pandas as pd
from ml.similarity.visual_embeddings import CardVisualEmbedder
from ml.utils.visual_coverage import compute_visual_coverage


def analyze_coverage(
    card_data_path: Path | str | None = None,
    image_url_map_path: Path | str | None = None,
    test_set_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Analyze visual embedding coverage.

    Args:
        card_data_path: Path to card_attributes_enriched.csv
        image_url_map_path: Path to image URL mapping JSON
        test_set_path: Path to test set JSON

    Returns:
        Dict with coverage statistics
    """
    # Load card data
    card_data = {}
    if card_data_path and Path(card_data_path).exists():
        df = pd.read_csv(card_data_path)
        for _, row in df.iterrows():
            card_name = row.get("NAME", "")
            if card_name:
                card_data[card_name] = row.to_dict()
        print(f"Loaded {len(card_data)} cards from {card_data_path}")

    # Load image URL map
    image_url_map = {}
    if image_url_map_path and Path(image_url_map_path).exists():
        with open(image_url_map_path) as f:
            image_url_map = json.load(f)
        print(f"Loaded {len(image_url_map)} image URLs from {image_url_map_path}")

    # Load test set
    test_set_cards = set()
    if test_set_path and Path(test_set_path).exists():
        with open(test_set_path) as f:
            test_data = json.load(f)
            for item in test_data:
                if "query" in item:
                    test_set_cards.add(item["query"])
                if "relevant" in item:
                    test_set_cards.update(item["relevant"])
        print(f"Loaded {len(test_set_cards)} unique cards from test set")

    # Initialize visual embedder
    try:
        embedder = CardVisualEmbedder()
        print(f"Initialized visual embedder with model: {embedder.model_name}")
    except Exception as e:
        print(f"⚠ Could not initialize visual embedder: {e}")
        return {"error": str(e)}

    # Compute coverage
    all_cards = list(card_data.keys()) if card_data else list(test_set_cards)
    coverage = compute_visual_coverage(embedder, card_data, all_cards)

    # Analyze test set coverage
    test_coverage = None
    if test_set_cards:
        test_coverage = compute_visual_coverage(embedder, card_data, list(test_set_cards))

    # Find cards missing images
    missing_images = []
    for card_name in all_cards[:1000]:  # Limit for performance
        card = card_data.get(card_name, {}) if card_data else {}
        image_url = embedder._get_image_url(card) if hasattr(embedder, "_get_image_url") else None
        if not image_url:
            missing_images.append(card_name)

    return {
        "overall_coverage": coverage,
        "test_set_coverage": test_coverage,
        "missing_images_sample": missing_images[:50],  # Sample
        "total_missing": len(missing_images),
    }


def print_report(stats: dict[str, Any]) -> None:
    """Print coverage report."""
    print("\n" + "=" * 60)
    print("Visual Embedding Coverage Report")
    print("=" * 60 + "\n")

    if "error" in stats:
        print(f"❌ Error: {stats['error']}")
        return

    # Overall coverage
    overall = stats.get("overall_coverage", {})
    print("Overall Coverage:")
    print(f"  Total cards analyzed: {overall.get('total_cards', 0)}")
    print(f"  Cards with images: {overall.get('cards_with_images', 0)}")
    print(f"  Coverage rate: {overall.get('coverage_rate', 0.0):.1%}")
    print(f"  Valid embeddings: {overall.get('valid_embeddings', 0)}")
    print(f"  Zero embeddings: {overall.get('zero_embeddings', 0)}")
    print(f"  Embedder available: {overall.get('embedder_available', False)}")

    # Test set coverage
    test = stats.get("test_set_coverage")
    if test:
        print("\nTest Set Coverage:")
        print(f"  Total test cards: {test.get('total_cards', 0)}")
        print(f"  Cards with images: {test.get('cards_with_images', 0)}")
        print(f"  Coverage rate: {test.get('coverage_rate', 0.0):.1%}")
        print(f"  Valid embeddings: {test.get('valid_embeddings', 0)}")
        print(f"  Zero embeddings: {test.get('zero_embeddings', 0)}")

    # Missing images
    missing = stats.get("missing_images_sample", [])
    total_missing = stats.get("total_missing", 0)
    print(f"\nMissing Images:")
    print(f"  Total missing: {total_missing}")
    if missing:
        print(f"  Sample (first 10): {', '.join(missing[:10])}")

    # Recommendations
    print("\n" + "=" * 60)
    print("Recommendations:")
    overall_rate = overall.get("coverage_rate", 0.0)
    if overall_rate < 0.1:
        print("  ⚠ Low coverage (<10%). Consider:")
        print("    - Fetching image URLs from Scryfall API")
        print("    - Using adaptive weights (already enabled)")
        print("    - Focusing on high-priority cards first")
    elif overall_rate < 0.5:
        print("  ⚠ Moderate coverage (10-50%). Consider:")
        print("    - Expanding image collection")
        print("    - Evaluating impact on high-coverage subset")
    else:
        print("  ✅ Good coverage (≥50%). Visual embeddings should be effective.")
    print("=" * 60 + "\n")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze visual embedding coverage")
    parser.add_argument(
        "--card-data",
        type=Path,
        default=Path("data/card_attributes_enriched.csv"),
        help="Path to card data CSV",
    )
    parser.add_argument(
        "--image-urls",
        type=Path,
        default=None,
        help="Path to image URL mapping JSON",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("data/test_set_minimal.json"),
        help="Path to test set JSON",
    )

    args = parser.parse_args()

    stats = analyze_coverage(
        card_data_path=args.card_data,
        image_url_map_path=args.image_urls,
        test_set_path=args.test_set,
    )

    print_report(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())

