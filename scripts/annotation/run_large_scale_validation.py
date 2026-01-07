#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
Large-Scale Validation of IAA and Uncertainty Selection

Generates 50+ annotations per method and compares:
1. Single annotator (baseline)
2. Uncertainty-based selection
3. Multi-annotator IAA

Validates improvements at scale.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ml.annotation.llm_annotator import LLMAnnotator


async def generate_large_scale_comparison(
    game: str = "magic",
    num_pairs: int = 50,
) -> dict:
    """Generate large-scale comparison across methods.

    Args:
        game: Game name
        num_pairs: Number of pairs per method

    Returns:
        Comparison results
    """
    print(f"\n{'='*70}")
    print(f"Large-Scale Validation: {game}")
    print(f"{'='*70}")
    print(f"Pairs per method: {num_pairs}")
    print()

    results = {}

    # Method 1: Single annotator (baseline)
    print(f"\n1. Single Annotator (Baseline)")
    print("-" * 70)
    annotator_single = LLMAnnotator(
        game=game,
        use_graph_enrichment=True,
        use_evoc_clustering=False,
        use_meta_judge=False,
        use_multi_annotator=False,
        use_uncertainty_selection=False,
        use_human_queue=False,
    )
    annotations_single = await annotator_single.annotate_similarity_pairs(
        num_pairs=num_pairs,
        strategy="diverse",
        batch_size=10,
    )
    results["single"] = analyze_annotations(annotations_single, "Single Annotator")

    # Method 2: Uncertainty-based selection
    print(f"\n2. Uncertainty-Based Selection")
    print("-" * 70)
    annotator_uncertainty = LLMAnnotator(
        game=game,
        use_graph_enrichment=True,
        use_evoc_clustering=False,
        use_meta_judge=False,
        use_multi_annotator=False,
        use_uncertainty_selection=True,
        use_human_queue=False,
    )
    annotations_uncertainty = await annotator_uncertainty.annotate_similarity_pairs(
        num_pairs=num_pairs,
        strategy="uncertainty",
        batch_size=10,
    )
    results["uncertainty"] = analyze_annotations(
        annotations_uncertainty, "Uncertainty Selection"
    )

    # Method 3: Multi-annotator IAA
    print(f"\n3. Multi-Annotator IAA")
    print("-" * 70)
    annotator_iaa = LLMAnnotator(
        game=game,
        use_graph_enrichment=True,
        use_evoc_clustering=False,
        use_meta_judge=False,
        use_multi_annotator=True,
        use_uncertainty_selection=False,
        use_human_queue=False,
    )
    annotations_iaa = await annotator_iaa.annotate_similarity_pairs(
        num_pairs=num_pairs,
        strategy="diverse",
        batch_size=5,  # Smaller batch for multi-annotator (3x LLM calls)
    )
    results["multi_annotator"] = analyze_annotations(
        annotations_iaa, "Multi-Annotator IAA"
    )

    # Comparison
    print(f"\n{'='*70}")
    print("Comparison Summary")
    print(f"{'='*70}\n")

    baseline = results["single"]
    for method, data in results.items():
        if method == "single":
            continue
        print(f"{method.upper()} vs BASELINE:")
        mean_diff = data["score_mean"] - baseline["score_mean"]
        std_diff = data["score_std"] - baseline["score_std"]
        print(f"  Mean: {mean_diff:+.3f} ({mean_diff/baseline['score_mean']*100:+.1f}%)")
        print(f"  Std: {std_diff:+.3f}")
        print()

    # Save results
    output_file = project_root / "annotations" / f"large_scale_validation_{game}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"✓ Results saved to: {output_file}")

    return results


def analyze_annotations(annotations: list, label: str) -> dict:
    """Analyze annotation batch.

    Args:
        annotations: List of annotations
        label: Method label

    Returns:
        Analysis dict
    """
    if not annotations:
        return {"error": "No annotations"}

    scores = []
    types = []
    sources = []

    for ann in annotations:
        if isinstance(ann, dict):
            scores.append(ann.get("similarity_score", 0.0))
            types.append(ann.get("similarity_type", "unknown"))
            sources.append(ann.get("source", "unknown"))
        else:
            scores.append(ann.similarity_score)
            types.append(ann.similarity_type)
            sources.append(ann.source if hasattr(ann, "source") else "unknown")

    score_ranges = {
        "very_low (0.0-0.2)": sum(1 for s in scores if 0.0 <= s < 0.2),
        "low (0.2-0.4)": sum(1 for s in scores if 0.2 <= s < 0.4),
        "medium (0.4-0.6)": sum(1 for s in scores if 0.4 <= s < 0.6),
        "high (0.6-0.8)": sum(1 for s in scores if 0.6 <= s < 0.8),
        "very_high (0.8-1.0)": sum(1 for s in scores if 0.8 <= s <= 1.0),
    }

    analysis = {
        "num_annotations": len(annotations),
        "score_mean": sum(scores) / len(scores) if scores else 0.0,
        "score_std": (
            sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
        ) ** 0.5
        if scores
        else 0.0,
        "score_min": min(scores) if scores else 0.0,
        "score_max": max(scores) if scores else 0.0,
        "score_distribution": score_ranges,
        "type_distribution": dict(Counter(types)),
        "source_distribution": dict(Counter(sources)),
    }

    print(f"  {label}:")
    print(f"    Annotations: {analysis['num_annotations']}")
    print(f"    Score: {analysis['score_mean']:.3f} ± {analysis['score_std']:.3f}")
    print(f"    Range: {analysis['score_min']:.3f} - {analysis['score_max']:.3f}")
    print(f"    Distribution:")
    for range_name, count in score_ranges.items():
        if count > 0:
            pct = (count / len(annotations)) * 100
            print(f"      {range_name}: {count} ({pct:.1f}%)")

    return analysis


if __name__ == "__main__":
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(description="Large-scale validation")
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh"],
        default="magic",
        help="Game to validate",
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=50,
        help="Number of pairs per method",
    )

    args = parser.parse_args()

    results = asyncio.run(
        generate_large_scale_comparison(game=args.game, num_pairs=args.num_pairs)
    )

    sys.exit(0)

