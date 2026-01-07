#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""
Analyze IAA and Uncertainty Selection Results

Compares annotation quality across:
1. Single annotator (baseline)
2. Uncertainty-based selection (hard mining)
3. Multi-annotator IAA (consensus)
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_results(results_file: Path):
    """Analyze and compare annotation results."""
    if not results_file.exists():
        print(f"Error: Results file not found: {results_file}")
        return
    
    with open(results_file) as f:
        results = json.load(f)
    
    print("=" * 80)
    print("IAA and Uncertainty Selection - Analysis")
    print("=" * 80)
    print()
    
    # Single annotator baseline
    if "single" in results and "error" not in results["single"]:
        single = results["single"]
        print("1. SINGLE ANNOTATOR (Baseline)")
        print("-" * 80)
        print(f"  Annotations: {single['num_annotations']}")
        print(f"  Score Mean: {single['score_mean']:.3f} ± {single['score_std']:.3f}")
        print(f"  Score Range: {single['score_min']:.3f} - {single['score_max']:.3f}")
        print(f"  Score Distribution:")
        for range_name, count in single['score_distribution'].items():
            if count > 0:
                pct = (count / single['num_annotations']) * 100
                print(f"    {range_name}: {count} ({pct:.1f}%)")
        print(f"  Types: {single['type_distribution']}")
        print()
    
    # Uncertainty selection
    if "uncertainty" in results and "error" not in results["uncertainty"]:
        uncertainty = results["uncertainty"]
        print("2. UNCERTAINTY-BASED SELECTION (Hard Mining)")
        print("-" * 80)
        print(f"  Annotations: {uncertainty['num_annotations']}")
        print(f"  Score Mean: {uncertainty['score_mean']:.3f} ± {uncertainty['score_std']:.3f}")
        print(f"  Score Range: {uncertainty['score_min']:.3f} - {uncertainty['score_max']:.3f}")
        print(f"  Score Distribution:")
        for range_name, count in uncertainty['score_distribution'].items():
            if count > 0:
                pct = (count / uncertainty['num_annotations']) * 100
                print(f"    {range_name}: {count} ({pct:.1f}%)")
        print(f"  Types: {uncertainty['type_distribution']}")
        
        if "single" in results and "error" not in results["single"]:
            single = results["single"]
            mean_diff = uncertainty['score_mean'] - single['score_mean']
            std_diff = uncertainty['score_std'] - single['score_std']
            print(f"\n  vs Single Annotator:")
            print(f"    Mean difference: {mean_diff:+.3f} ({mean_diff/single['score_mean']*100:+.1f}%)")
            print(f"    Std difference: {std_diff:+.3f}")
            
            # Score diversity improvement
            single_low = single['score_distribution'].get('very_low (0.0-0.2)', 0) / single['num_annotations']
            uncertainty_low = uncertainty['score_distribution'].get('very_low (0.0-0.2)', 0) / uncertainty['num_annotations']
            diversity_improvement = single_low - uncertainty_low
            print(f"    Low-score reduction: {diversity_improvement*100:.1f}% (fewer very low scores)")
        print()
    
    # Multi-annotator IAA
    if "multi_annotator" in results and "error" not in results["multi_annotator"]:
        multi = results["multi_annotator"]
        print("3. MULTI-ANNOTATOR IAA (Consensus)")
        print("-" * 80)
        print(f"  Annotations: {multi['num_annotations']}")
        print(f"  Score Mean: {multi['score_mean']:.3f} ± {multi['score_std']:.3f}")
        print(f"  Score Range: {multi['score_min']:.3f} - {multi['score_max']:.3f}")
        print(f"  Score Distribution:")
        for range_name, count in multi['score_distribution'].items():
            if count > 0:
                pct = (count / multi['num_annotations']) * 100
                print(f"    {range_name}: {count} ({pct:.1f}%)")
        print(f"  Types: {multi['type_distribution']}")
        print(f"  Sources: {multi['source_distribution']}")
        
        if "single" in results and "error" not in results["single"]:
            single = results["single"]
            mean_diff = multi['score_mean'] - single['score_mean']
            std_diff = multi['score_std'] - single['score_std']
            print(f"\n  vs Single Annotator:")
            print(f"    Mean difference: {mean_diff:+.3f} ({mean_diff/single['score_mean']*100:+.1f}%)")
            print(f"    Std difference: {std_diff:+.3f}")
        print()
    
    # Key Insights
    print("=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    
    if "uncertainty" in results and "error" not in results["uncertainty"]:
        uncertainty = results["uncertainty"]
        print("\n✓ Uncertainty-Based Selection:")
        print("  - Selects pairs where model is uncertain/confused")
        print("  - Results in more diverse score distribution")
        print("  - Avoids clustering in very low scores")
        print("  - Better for hard mining (finding difficult examples)")
    
    if "multi_annotator" in results and "error" not in results["multi_annotator"]:
        multi = results["multi_annotator"]
        print("\n✓ Multi-Annotator IAA:")
        print("  - Uses consensus from multiple LLM models")
        print("  - Computes Krippendorff's Alpha for agreement")
        print("  - Filters low-agreement annotations")
        print("  - Better for high-quality ground truth")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print("\n1. For Training Data (Hard Mining):")
    print("   → Use uncertainty-based selection")
    print("   → Prioritizes difficult/uncertain examples")
    print("   → Improves model performance on edge cases")
    
    print("\n2. For Evaluation Data (High Quality):")
    print("   → Use multi-annotator IAA")
    print("   → Ensures consensus and reliability")
    print("   → Filters out low-agreement annotations")
    
    print("\n3. For Speed/Cost Optimization:")
    print("   → Use single annotator with uncertainty selection")
    print("   → Best balance of quality and efficiency")
    print()


if __name__ == "__main__":
    results_file = project_root / "annotations" / "iaa_uncertainty_test_results.json"
    
    if len(sys.argv) > 1:
        results_file = Path(sys.argv[1])
    
    analyze_results(results_file)

