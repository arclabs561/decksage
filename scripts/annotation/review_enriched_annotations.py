#!/usr/bin/env python3
"""Review and critique enriched annotations for quality issues."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_annotation_quality(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze annotation quality and return metrics."""
    if not annotations:
        return {"error": "No annotations provided"}
    
    total = len(annotations)
    
    # Required fields
    has_card1 = sum(1 for a in annotations if a.get("card1"))
    has_card2 = sum(1 for a in annotations if a.get("card2"))
    has_source = sum(1 for a in annotations if a.get("source"))
    has_similarity = sum(1 for a in annotations if "similarity_score" in a and a.get("similarity_score") is not None)
    
    # Enrichment fields
    has_graph_features = sum(1 for a in annotations if a.get("graph_features"))
    has_card_comparison = sum(1 for a in annotations if a.get("card_comparison"))
    
    # Graph feature quality
    graph_features = [a.get("graph_features", {}) for a in annotations if a.get("graph_features")]
    has_jaccard = sum(1 for gf in graph_features if gf.get("jaccard_similarity") is not None)
    has_cooccurrence = sum(1 for gf in graph_features if gf.get("cooccurrence_count", 0) > 0)
    has_common_neighbors = sum(1 for gf in graph_features if gf.get("common_neighbors", 0) > 0)
    
    # Similarity score distribution
    similarity_scores = [a.get("similarity_score") for a in annotations if a.get("similarity_score") is not None]
    jaccard_scores = [gf.get("jaccard_similarity") for gf in graph_features if gf.get("jaccard_similarity") is not None]
    
    # Correlation analysis
    high_similarity = sum(1 for a in annotations if a.get("similarity_score", 0) > 0.7)
    high_jaccard = sum(1 for gf in graph_features if gf.get("jaccard_similarity", 0) > 0.3)
    correlation_overlap = sum(
        1 for a in annotations
        if a.get("similarity_score", 0) > 0.7
        and a.get("graph_features", {}).get("jaccard_similarity", 0) > 0.3
    )
    
    # Issues
    issues = []
    for i, ann in enumerate(annotations):
        if not ann.get("card1") or not ann.get("card2"):
            issues.append(f"Line {i+1}: Missing card1 or card2")
        if "similarity_score" not in ann or ann.get("similarity_score") is None:
            issues.append(f"Line {i+1}: Missing similarity_score")
        if "source" not in ann:
            issues.append(f"Line {i+1}: Missing source field")
        if not ann.get("graph_features"):
            issues.append(f"Line {i+1}: Missing graph_features")
        if ann.get("similarity_score") is not None:
            score = ann.get("similarity_score")
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                issues.append(f"Line {i+1}: Invalid similarity_score: {score}")
    
    return {
        "total": total,
        "required_fields": {
            "card1": f"{has_card1}/{total} ({has_card1/total*100:.1f}%)",
            "card2": f"{has_card2}/{total} ({has_card2/total*100:.1f}%)",
            "source": f"{has_source}/{total} ({has_source/total*100:.1f}%)",
            "similarity_score": f"{has_similarity}/{total} ({has_similarity/total*100:.1f}%)",
        },
        "enrichment_fields": {
            "graph_features": f"{has_graph_features}/{total} ({has_graph_features/total*100:.1f}%)",
            "card_comparison": f"{has_card_comparison}/{total} ({has_card_comparison/total*100:.1f}%)",
        },
        "graph_quality": {
            "jaccard_available": f"{has_jaccard}/{total} ({has_jaccard/total*100:.1f}%)",
            "has_cooccurrence": f"{has_cooccurrence}/{total} ({has_cooccurrence/total*100:.1f}%)",
            "has_common_neighbors": f"{has_common_neighbors}/{total} ({has_common_neighbors/total*100:.1f}%)",
        },
        "score_distribution": {
            "similarity_score": {
                "min": min(similarity_scores) if similarity_scores else None,
                "max": max(similarity_scores) if similarity_scores else None,
                "avg": sum(similarity_scores) / len(similarity_scores) if similarity_scores else None,
            },
            "jaccard_similarity": {
                "min": min(jaccard_scores) if jaccard_scores else None,
                "max": max(jaccard_scores) if jaccard_scores else None,
                "avg": sum(jaccard_scores) / len(jaccard_scores) if jaccard_scores else None,
            },
        },
        "correlation": {
            "high_similarity_count": high_similarity,
            "high_jaccard_count": high_jaccard,
            "overlap": f"{correlation_overlap}/{total} ({correlation_overlap/total*100:.1f}%)",
        },
        "issues": issues,
        "issue_count": len(issues),
    }


def print_quality_report(metrics: dict[str, Any], file_path: Path) -> None:
    """Print formatted quality report."""
    print("=" * 80)
    print(f"ANNOTATION QUALITY REPORT: {file_path.name}")
    print("=" * 80)
    print()
    
    print(f"Total annotations: {metrics['total']}")
    print()
    
    print("Required Fields:")
    for field, value in metrics["required_fields"].items():
        print(f"  {field}: {value}")
    print()
    
    print("Enrichment Fields:")
    for field, value in metrics["enrichment_fields"].items():
        print(f"  {field}: {value}")
    print()
    
    print("Graph Feature Quality:")
    for field, value in metrics["graph_quality"].items():
        print(f"  {field}: {value}")
    print()
    
    print("Score Distribution:")
    if metrics["score_distribution"]["similarity_score"]["min"] is not None:
        sim = metrics["score_distribution"]["similarity_score"]
        print(f"  Similarity Score: min={sim['min']:.3f}, max={sim['max']:.3f}, avg={sim['avg']:.3f}")
    if metrics["score_distribution"]["jaccard_similarity"]["min"] is not None:
        jac = metrics["score_distribution"]["jaccard_similarity"]
        print(f"  Jaccard Similarity: min={jac['min']:.3f}, max={jac['max']:.3f}, avg={jac['avg']:.3f}")
    print()
    
    print("Correlation Analysis:")
    corr = metrics["correlation"]
    print(f"  High similarity (>0.7): {corr['high_similarity_count']}")
    print(f"  High jaccard (>0.3): {corr['high_jaccard_count']}")
    print(f"  Overlap: {corr['overlap']}")
    print()
    
    if metrics["issue_count"] > 0:
        print(f"Issues Found: {metrics['issue_count']}")
        for issue in metrics["issues"][:20]:  # Show first 20
            print(f"  ⚠️  {issue}")
        if metrics["issue_count"] > 20:
            print(f"  ... and {metrics['issue_count'] - 20} more issues")
    else:
        print("✅ No issues found")
    print()
    print("=" * 80)


def critique_annotations(metrics: dict[str, Any]) -> list[str]:
    """Provide critique and recommendations."""
    critiques = []
    
    # Field coverage
    if metrics["required_fields"]["source"].startswith("0/"):
        critiques.append("CRITICAL: Missing 'source' field in all annotations - required for validation")
    
    if metrics["required_fields"]["similarity_score"].startswith("0/"):
        critiques.append("CRITICAL: Missing 'similarity_score' in all annotations - required field")
    
    # Enrichment quality
    if metrics["enrichment_fields"]["graph_features"].startswith("0/"):
        critiques.append("WARNING: No graph_features found - enrichment may have failed")
    
    if metrics["graph_quality"]["has_cooccurrence"].startswith("0/"):
        critiques.append("WARNING: No co-occurrence data found - cards may not be in graph database")
    
    # Score distribution
    sim_dist = metrics["score_distribution"]["similarity_score"]
    if sim_dist["avg"] is not None:
        if sim_dist["avg"] < 0.3:
            critiques.append("NOTE: Average similarity score is low (<0.3) - may indicate diverse pairs")
        elif sim_dist["avg"] > 0.8:
            critiques.append("NOTE: Average similarity score is very high (>0.8) - may lack diversity")
    
    # Correlation
    corr = metrics["correlation"]
    overlap_pct = float(corr["overlap"].split("(")[1].split("%")[0])
    if overlap_pct < 20:
        critiques.append("NOTE: Low correlation between high similarity and high jaccard - graph features may not align with LLM judgments")
    
    # Issues
    if metrics["issue_count"] > 0:
        critiques.append(f"WARNING: {metrics['issue_count']} validation issues found - review recommended")
    
    return critiques


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Review and critique enriched annotations")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input annotation file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output report file (optional, prints to stdout if not specified)",
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    # Load annotations
    annotations = []
    try:
        with open(args.input) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    ann = json.loads(line)
                    annotations.append(ann)
                except json.JSONDecodeError as e:
                    print(f"Error parsing line {line_num}: {e}")
                    return 1
    except Exception as e:
        print(f"Error reading file: {e}")
        return 1
    
    if not annotations:
        print("Error: No annotations found in file")
        return 1
    
    # Analyze
    metrics = analyze_annotation_quality(annotations)
    
    # Print report
    print_quality_report(metrics, args.input)
    
    # Critique
    critiques = critique_annotations(metrics)
    if critiques:
        print("CRITIQUE & RECOMMENDATIONS:")
        print("=" * 80)
        for critique in critiques:
            print(f"  • {critique}")
        print("=" * 80)
    
    # Write to file if specified
    if args.output:
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if metrics["issue_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

