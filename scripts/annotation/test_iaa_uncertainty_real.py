#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
Test IAA and Uncertainty Selection with Real Annotations

Generates small batches of annotations using:
1. Single annotator (baseline)
2. Multi-annotator IAA (consensus)
3. Uncertainty-based selection (hard mining)

Then analyzes and compares the results.
"""

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ml.annotation.llm_annotator import LLMAnnotator


async def generate_and_analyze(
    annotator: LLMAnnotator,
    strategy: str,
    num_pairs: int = 5,
    label: str = "",
) -> dict:
    """Generate annotations and analyze results."""
    print(f"\n{'='*60}")
    print(f"Generating {num_pairs} annotations: {label}")
    print(f"{'='*60}")
    
    annotations = await annotator.annotate_similarity_pairs(
        num_pairs=num_pairs,
        strategy=strategy,
        batch_size=2,  # Small batches for testing
    )
    
    if not annotations:
        return {"error": "No annotations generated"}
    
    # Analyze annotations
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
    
    # Score distribution
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
        "score_std": (sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores))**0.5 if scores else 0.0,
        "score_min": min(scores) if scores else 0.0,
        "score_max": max(scores) if scores else 0.0,
        "score_distribution": score_ranges,
        "type_distribution": dict(Counter(types)),
        "source_distribution": dict(Counter(sources)),
    }
    
    print(f"\n  Generated: {len(annotations)} annotations")
    print(f"  Score range: {analysis['score_min']:.3f} - {analysis['score_max']:.3f}")
    print(f"  Score mean: {analysis['score_mean']:.3f} ± {analysis['score_std']:.3f}")
    print(f"  Score distribution:")
    for range_name, count in score_ranges.items():
        if count > 0:
            print(f"    {range_name}: {count}")
    print(f"  Types: {dict(Counter(types))}")
    print(f"  Sources: {dict(Counter(sources))}")
    
    return analysis


async def main():
    """Run comparison tests."""
    print("\n" + "="*60)
    print("IAA and Uncertainty Selection - Real Annotation Test")
    print("="*60)
    
    # Check for API key
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        print("\n⚠ Warning: OPENROUTER_API_KEY not set")
        print("  Set in .env file or: export OPENROUTER_API_KEY=your-key")
        print("  Skipping actual LLM calls, testing infrastructure only...")
        return 0
    
    results = {}
    
    # Test 1: Single annotator (baseline)
    try:
        annotator_single = LLMAnnotator(
            game="magic",
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=False,
            use_uncertainty_selection=False,
        )
        results["single"] = await generate_and_analyze(
            annotator_single,
            strategy="diverse",
            num_pairs=5,
            label="Single Annotator (Baseline)",
        )
    except Exception as e:
        print(f"✗ Single annotator test failed: {e}")
        import traceback
        traceback.print_exc()
        results["single"] = {"error": str(e)}
    
    # Test 2: Uncertainty-based selection
    try:
        annotator_uncertainty = LLMAnnotator(
            game="magic",
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=False,
            use_uncertainty_selection=True,
        )
        results["uncertainty"] = await generate_and_analyze(
            annotator_uncertainty,
            strategy="uncertainty",
            num_pairs=5,
            label="Uncertainty-Based Selection (Hard Mining)",
        )
    except Exception as e:
        print(f"✗ Uncertainty selection test failed: {e}")
        import traceback
        traceback.print_exc()
        results["uncertainty"] = {"error": str(e)}
    
    # Test 3: Multi-annotator IAA
    try:
        annotator_iaa = LLMAnnotator(
            game="magic",
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=True,
            use_uncertainty_selection=False,
        )
        results["multi_annotator"] = await generate_and_analyze(
            annotator_iaa,
            strategy="diverse",
            num_pairs=5,
            label="Multi-Annotator IAA (Consensus)",
        )
    except Exception as e:
        print(f"✗ Multi-annotator test failed: {e}")
        import traceback
        traceback.print_exc()
        results["multi_annotator"] = {"error": str(e)}
    
    # Comparison
    print(f"\n{'='*60}")
    print("Comparison Summary")
    print(f"{'='*60}")
    
    if "single" in results and "error" not in results["single"]:
        print(f"\nSingle Annotator:")
        print(f"  Mean score: {results['single']['score_mean']:.3f}")
        print(f"  Score std: {results['single']['score_std']:.3f}")
    
    if "uncertainty" in results and "error" not in results["uncertainty"]:
        print(f"\nUncertainty Selection:")
        print(f"  Mean score: {results['uncertainty']['score_mean']:.3f}")
        print(f"  Score std: {results['uncertainty']['score_std']:.3f}")
        if "single" in results and "error" not in results["single"]:
            diff = results['uncertainty']['score_mean'] - results['single']['score_mean']
            print(f"  vs Single: {diff:+.3f}")
    
    if "multi_annotator" in results and "error" not in results["multi_annotator"]:
        print(f"\nMulti-Annotator IAA:")
        print(f"  Mean score: {results['multi_annotator']['score_mean']:.3f}")
        print(f"  Score std: {results['multi_annotator']['score_std']:.3f}")
        if "single" in results and "error" not in results["single"]:
            diff = results['multi_annotator']['score_mean'] - results['single']['score_mean']
            print(f"  vs Single: {diff:+.3f}")
    
    # Save results
    output_file = project_root / "annotations" / "iaa_uncertainty_test_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

