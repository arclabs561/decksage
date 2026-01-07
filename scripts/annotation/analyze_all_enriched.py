#!/usr/bin/env python3
"""Comprehensive analysis of all enriched annotations across games."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_all_files(annotations_dir: Path) -> dict:
    """Analyze all enriched annotation files."""
    files = [
        "magic_llm_annotations_enriched.jsonl",
        "yugioh_llm_annotations_enriched.jsonl",
        "pokemon_llm_annotations_enriched.jsonl",
        "riftbound_llm_annotations_enriched.jsonl",
    ]
    
    all_annotations = []
    file_stats = {}
    
    for filename in files:
        filepath = annotations_dir / filename
        if not filepath.exists():
            continue
        
        annotations = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    annotations.append(json.loads(line))
        
        all_annotations.extend(annotations)
        file_stats[filename] = {
            "count": len(annotations),
            "game": annotations[0].get("game") if annotations else None,
        }
    
    # Cross-file analysis
    unique_pairs = set(
        (a.get("card1"), a.get("card2"))
        for a in all_annotations
        if a.get("card1") and a.get("card2")
    )
    
    games = set(a.get("game") for a in all_annotations if a.get("game"))
    sources = Counter(a.get("source") for a in all_annotations if a.get("source"))
    
    # Similarity score distribution
    similarity_scores = [a.get("similarity_score") for a in all_annotations if a.get("similarity_score") is not None]
    
    # Graph feature coverage
    has_cooccurrence = sum(1 for a in all_annotations if a.get("graph_features", {}).get("cooccurrence_count", 0) > 0)
    has_common_neighbors = sum(1 for a in all_annotations if a.get("graph_features", {}).get("common_neighbors", 0) > 0)
    
    return {
        "total_annotations": len(all_annotations),
        "unique_pairs": len(unique_pairs),
        "games": list(games),
        "sources": dict(sources),
        "file_stats": file_stats,
        "similarity_distribution": {
            "min": min(similarity_scores) if similarity_scores else None,
            "max": max(similarity_scores) if similarity_scores else None,
            "avg": sum(similarity_scores) / len(similarity_scores) if similarity_scores else None,
            "unique_values": len(set(similarity_scores)),
        },
        "graph_coverage": {
            "has_cooccurrence": f"{has_cooccurrence}/{len(all_annotations)} ({has_cooccurrence/len(all_annotations)*100:.1f}%)",
            "has_common_neighbors": f"{has_common_neighbors}/{len(all_annotations)} ({has_common_neighbors/len(all_annotations)*100:.1f}%)",
        },
    }


def print_analysis(analysis: dict) -> None:
    """Print formatted analysis."""
    print("=" * 80)
    print("COMPREHENSIVE ENRICHED ANNOTATION ANALYSIS")
    print("=" * 80)
    print()
    
    print(f"Total annotations: {analysis['total_annotations']}")
    print(f"Unique card pairs: {analysis['unique_pairs']}")
    print(f"Games covered: {', '.join(analysis['games'])}")
    print(f"Sources: {analysis['sources']}")
    print()
    
    print("File Statistics:")
    for filename, stats in analysis["file_stats"].items():
        print(f"  {filename}: {stats['count']} annotations ({stats['game']})")
    print()
    
    print("Similarity Score Distribution:")
    sim = analysis["similarity_distribution"]
    if sim["min"] is not None:
        print(f"  Range: {sim['min']:.3f} - {sim['max']:.3f}")
        print(f"  Average: {sim['avg']:.3f}")
        print(f"  Unique values: {sim['unique_values']}")
        if sim["unique_values"] == 1:
            print(f"  ⚠️  WARNING: All annotations have same similarity score!")
    print()
    
    print("Graph Feature Coverage:")
    for key, value in analysis["graph_coverage"].items():
        print(f"  {key}: {value}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    annotations_dir = Path("annotations")
    if not annotations_dir.exists():
        print(f"Error: Annotations directory not found: {annotations_dir}")
        sys.exit(1)
    
    analysis = analyze_all_files(annotations_dir)
    print_analysis(analysis)

