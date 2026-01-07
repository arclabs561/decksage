#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
Continuous Improvement Loop for Annotation System

Runs iterative improvement cycle:
1. Generate annotations with current system
2. Analyze quality (score distribution, IAA, meta-judge feedback)
3. Identify issues (clustering, low IAA, poor reasoning)
4. Apply improvements (prompt refinement, pair selection, model params)
5. Test improvements
6. Repeat

This implements the "keep improving and refining" workflow.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from src.ml.annotation.llm_annotator import LLMAnnotator
from src.ml.annotation.meta_judge import meta_judge_annotations, inject_context_into_annotator
from src.ml.utils.paths import PATHS


def analyze_annotation_quality(annotations: list) -> dict:
    """Analyze annotation quality metrics."""
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
            sources.append(getattr(ann, "source", "unknown"))
    
    # Score distribution
    score_ranges = {
        "very_low (0.0-0.2)": sum(1 for s in scores if 0.0 <= s < 0.2),
        "low (0.2-0.4)": sum(1 for s in scores if 0.2 <= s < 0.4),
        "medium (0.4-0.6)": sum(1 for s in scores if 0.4 <= s < 0.6),
        "high (0.6-0.8)": sum(1 for s in scores if 0.6 <= s < 0.8),
        "very_high (0.8-1.0)": sum(1 for s in scores if 0.8 <= s <= 1.0),
    }
    
    # Calculate metrics
    mean_score = sum(scores) / len(scores) if scores else 0.0
    std_score = (sum((s - mean_score)**2 for s in scores) / len(scores))**0.5 if scores else 0.0
    
    # Identify issues
    issues = []
    
    # Check for clustering
    very_low_pct = score_ranges["very_low (0.0-0.2)"] / len(scores) * 100
    very_high_pct = score_ranges["very_high (0.8-1.0)"] / len(scores) * 100
    
    if very_low_pct > 50:
        issues.append(f"Score clustering in very_low range ({very_low_pct:.1f}%)")
    if very_high_pct > 50:
        issues.append(f"Score clustering in very_high range ({very_high_pct:.1f}%)")
    
    # Check score diversity
    if std_score < 0.15:
        issues.append(f"Low score diversity (std={std_score:.3f})")
    
    # Check range utilization
    used_ranges = sum(1 for count in score_ranges.values() if count > 0)
    if used_ranges < 3:
        issues.append(f"Limited range utilization ({used_ranges}/5 ranges used)")
    
    return {
        "num_annotations": len(annotations),
        "score_mean": mean_score,
        "score_std": std_score,
        "score_min": min(scores) if scores else 0.0,
        "score_max": max(scores) if scores else 0.0,
        "score_distribution": score_ranges,
        "type_distribution": dict(Counter(types)),
        "source_distribution": dict(Counter(sources)),
        "issues": issues,
        "range_utilization": used_ranges,
    }


async def generate_and_improve(
    game: str = "magic",
    num_pairs: int = 10,
    iterations: int = 3,
    use_multi_annotator: bool = True,
    use_meta_judge: bool = True,
) -> dict:
    """Generate annotations and iteratively improve."""
    print("="*70)
    print(f"Continuous Improvement Loop: {game}")
    print("="*70)
    print(f"Iterations: {iterations}, Pairs per iteration: {num_pairs}")
    print()
    
    all_results = []
    annotator = None
    
    for iteration in range(iterations):
        print(f"\n{'='*70}")
        print(f"Iteration {iteration + 1}/{iterations}")
        print(f"{'='*70}")
        
        # Initialize or update annotator
        if annotator is None:
            annotator = LLMAnnotator(
                game=game,
                use_graph_enrichment=True,
                use_evoc_clustering=True,
                use_meta_judge=use_meta_judge,
                use_multi_annotator=use_multi_annotator,
                use_uncertainty_selection=False,
                use_human_queue=False,
            )
        else:
            # Re-initialize to get updated prompts from meta-judge
            annotator = LLMAnnotator(
                game=game,
                use_graph_enrichment=True,
                use_evoc_clustering=True,
                use_meta_judge=use_meta_judge,
                use_multi_annotator=use_multi_annotator,
                use_uncertainty_selection=False,
                use_human_queue=False,
            )
        
        # Generate annotations
        print(f"\nGenerating {num_pairs} annotations...")
        annotations = await annotator.annotate_similarity_pairs(
            num_pairs=num_pairs,
            strategy="diverse",
            batch_size=5,
        )
        
        if not annotations:
            print("  ✗ No annotations generated")
            continue
        
        # Analyze quality
        print(f"\nAnalyzing quality...")
        analysis = analyze_annotation_quality(annotations)
        
        print(f"  Annotations: {analysis['num_annotations']}")
        print(f"  Score: {analysis['score_mean']:.3f} ± {analysis['score_std']:.3f}")
        print(f"  Range: {analysis['score_min']:.3f} - {analysis['score_max']:.3f}")
        print(f"  Range utilization: {analysis['range_utilization']}/5")
        
        if analysis['issues']:
            print(f"  Issues found:")
            for issue in analysis['issues']:
                print(f"    - {issue}")
        else:
            print(f"  ✅ No major issues detected")
        
        # Meta-judge feedback (if enabled)
        if use_meta_judge and annotations:
            print(f"\nRunning meta-judge...")
            try:
                # Convert to dict format for meta-judge
                annotations_dict = []
                for ann in annotations:
                    if isinstance(ann, dict):
                        annotations_dict.append(ann)
                    else:
                        annotations_dict.append(ann.model_dump())
                
                feedback = await meta_judge_annotations(
                    annotations_dict,
                    game=game,
                )
                
                if feedback and feedback.get("issues"):
                    print(f"  Meta-judge found {len(feedback['issues'])} issues:")
                    for issue in feedback['issues'][:3]:  # Show first 3
                        print(f"    - {issue.get('type', 'unknown')}: {issue.get('description', '')[:60]}")
                
                # Inject context for next iteration
                if feedback:
                    inject_context_into_annotator(annotator, feedback)
                    print(f"  ✅ Context injected for next iteration")
                    
            except Exception as e:
                print(f"  ⚠️ Meta-judge failed: {e}")
        
        # Save iteration results
        iteration_result = {
            "iteration": iteration + 1,
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "num_annotations": len(annotations),
        }
        all_results.append(iteration_result)
        
        # Save annotations
        output_file = project_root / "annotations" / f"{game}_improvement_iter_{iteration+1}.jsonl"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            for ann in annotations:
                if isinstance(ann, dict):
                    f.write(json.dumps(ann) + "\n")
                else:
                    f.write(ann.model_dump_json() + "\n")
        print(f"\n  ✓ Saved to: {output_file}")
    
    # Final summary
    print(f"\n{'='*70}")
    print("Improvement Summary")
    print(f"{'='*70}")
    
    for result in all_results:
        analysis = result['analysis']
        print(f"\nIteration {result['iteration']}:")
        print(f"  Score: {analysis['score_mean']:.3f} ± {analysis['score_std']:.3f}")
        print(f"  Range utilization: {analysis['range_utilization']}/5")
        if analysis['issues']:
            print(f"  Issues: {len(analysis['issues'])}")
    
    # Save summary
    summary_file = project_root / "annotations" / f"{game}_improvement_summary.json"
    with open(summary_file, "w") as f:
        json.dump({
            "game": game,
            "iterations": iterations,
            "pairs_per_iteration": num_pairs,
            "results": all_results,
        }, f, indent=2, default=str)
    
    print(f"\n✓ Summary saved to: {summary_file}")
    
    return {
        "game": game,
        "iterations": iterations,
        "results": all_results,
    }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Continuous improvement loop for annotation system",
    )
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh"],
        default="magic",
        help="Game to improve",
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=10,
        help="Number of pairs per iteration",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of improvement iterations",
    )
    parser.add_argument(
        "--no-multi-annotator",
        action="store_true",
        help="Disable multi-annotator IAA",
    )
    parser.add_argument(
        "--no-meta-judge",
        action="store_true",
        help="Disable meta-judge feedback",
    )

    args = parser.parse_args()

    results = await generate_and_improve(
        game=args.game,
        num_pairs=args.num_pairs,
        iterations=args.iterations,
        use_multi_annotator=not args.no_multi_annotator,
        use_meta_judge=not args.no_meta_judge,
    )

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

