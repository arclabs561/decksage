#!/usr/bin/env python3
"""Track annotation usage across the system.

Monitors:
- Which annotations are used in training
- Which annotations are queried via API
- Which annotations are integrated into graph
- Usage statistics and trends
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.annotation_utils import load_similarity_annotations
from ml.utils.paths import PATHS


def load_usage_tracking() -> dict:
    """Load usage tracking data."""
    # Use annotations directory from project root
    annotations_dir = Path(__file__).parent.parent.parent / "annotations"
    tracking_file = annotations_dir / "usage_tracking.json"
    if tracking_file.exists():
        with open(tracking_file) as f:
            return json.load(f)
    return {
        "training_usage": {},
        "api_queries": {},
        "graph_integration": {},
        "last_updated": None,
    }


def save_usage_tracking(data: dict) -> None:
    """Save usage tracking data."""
    tracking_file = PATHS.annotations_dir / "usage_tracking.json"
    tracking_file.parent.mkdir(parents=True, exist_ok=True)
    
    data["last_updated"] = datetime.now().isoformat()
    
    temp_file = tracking_file.with_suffix(".tmp")
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    temp_file.replace(tracking_file)


def track_training_usage(annotation_file: Path, pairs_used: list[tuple[str, str]]) -> None:
    """Track which annotations were used in training."""
    tracking = load_usage_tracking()
    
    file_key = str(annotation_file.relative_to(PATHS.annotations_dir))
    if file_key not in tracking["training_usage"]:
        tracking["training_usage"][file_key] = {
            "first_used": datetime.now().isoformat(),
            "usage_count": 0,
            "pairs_used": set(),
        }
    
    tracking["training_usage"][file_key]["usage_count"] += 1
    tracking["training_usage"][file_key]["pairs_used"].update(
        [f"{c1}|||{c2}" for c1, c2 in pairs_used]
    )
    tracking["training_usage"][file_key]["last_used"] = datetime.now().isoformat()
    
    # Convert sets to lists for JSON
    for key in tracking["training_usage"]:
        if "pairs_used" in tracking["training_usage"][key]:
            tracking["training_usage"][key]["pairs_used"] = list(
                tracking["training_usage"][key]["pairs_used"]
            )
    
    save_usage_tracking(tracking)


def track_api_query(card1: str, card2: str, annotation_file: Path | None = None) -> None:
    """Track API queries for annotation pairs."""
    tracking = load_usage_tracking()
    
    pair_key = f"{card1}|||{card2}"
    if pair_key not in tracking["api_queries"]:
        tracking["api_queries"][pair_key] = {
            "first_queried": datetime.now().isoformat(),
            "query_count": 0,
            "annotation_source": str(annotation_file) if annotation_file else None,
        }
    
    tracking["api_queries"][pair_key]["query_count"] += 1
    tracking["api_queries"][pair_key]["last_queried"] = datetime.now().isoformat()
    
    save_usage_tracking(tracking)


def track_graph_integration(annotation_file: Path, pairs_integrated: int) -> None:
    """Track graph integration of annotations."""
    tracking = load_usage_tracking()
    
    file_key = str(annotation_file.relative_to(PATHS.annotations_dir))
    if file_key not in tracking["graph_integration"]:
        tracking["graph_integration"][file_key] = {
            "first_integrated": datetime.now().isoformat(),
            "integration_count": 0,
            "pairs_integrated": 0,
        }
    
    tracking["graph_integration"][file_key]["integration_count"] += 1
    tracking["graph_integration"][file_key]["pairs_integrated"] = pairs_integrated
    tracking["graph_integration"][file_key]["last_integrated"] = datetime.now().isoformat()
    
    save_usage_tracking(tracking)


def generate_usage_report() -> dict:
    """Generate usage statistics report."""
    tracking = load_usage_tracking()
    
    report = {
        "summary": {
            "total_training_files": len(tracking.get("training_usage", {})),
            "total_api_queries": len(tracking.get("api_queries", {})),
            "total_graph_integrations": len(tracking.get("graph_integration", {})),
            "last_updated": tracking.get("last_updated"),
        },
        "training_usage": {},
        "api_usage": {},
        "graph_integration": {},
    }
    
    # Training usage stats
    for file_key, usage in tracking.get("training_usage", {}).items():
        report["training_usage"][file_key] = {
            "usage_count": usage.get("usage_count", 0),
            "pairs_used": len(usage.get("pairs_used", [])),
            "first_used": usage.get("first_used"),
            "last_used": usage.get("last_used"),
        }
    
    # API usage stats
    total_api_queries = sum(
        q.get("query_count", 0) for q in tracking.get("api_queries", {}).values()
    )
    report["api_usage"] = {
        "unique_pairs_queried": len(tracking.get("api_queries", {})),
        "total_queries": total_api_queries,
    }
    
    # Graph integration stats
    for file_key, integration in tracking.get("graph_integration", {}).items():
        report["graph_integration"][file_key] = {
            "integration_count": integration.get("integration_count", 0),
            "pairs_integrated": integration.get("pairs_integrated", 0),
            "first_integrated": integration.get("first_integrated"),
            "last_integrated": integration.get("last_integrated"),
        }
    
    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Track annotation usage")
    parser.add_argument(
        "command",
        choices=["report", "track-training", "track-api", "track-graph"],
        help="Command to execute",
    )
    parser.add_argument(
        "--annotation-file",
        type=Path,
        help="Annotation file to track",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        help="Card pairs (format: card1|||card2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output report file",
    )

    args = parser.parse_args()

    if args.command == "report":
        report = generate_usage_report()
        
        print("=" * 80)
        print("ANNOTATION USAGE REPORT")
        print("=" * 80)
        print()
        print(f"Summary:")
        print(f"  Training files used: {report['summary']['total_training_files']}")
        print(f"  API queries: {report['summary']['total_api_queries']}")
        print(f"  Graph integrations: {report['summary']['total_graph_integrations']}")
        print(f"  Last updated: {report['summary']['last_updated']}")
        print()
        
        if report["training_usage"]:
            print("Training Usage:")
            for file_key, usage in report["training_usage"].items():
                print(f"  {file_key}:")
                print(f"    Used {usage['usage_count']} times")
                print(f"    {usage['pairs_used']} pairs used")
        
        if report["api_usage"]:
            print("\nAPI Usage:")
            print(f"  Unique pairs queried: {report['api_usage']['unique_pairs_queried']}")
            print(f"  Total queries: {report['api_usage']['total_queries']}")
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\nReport saved to: {args.output}")
    
    elif args.command == "track-training":
        if not args.annotation_file or not args.pairs:
            print("Error: --annotation-file and --pairs required")
            return 1
        
        pairs = [tuple(p.split("|||")) for p in args.pairs]
        track_training_usage(args.annotation_file, pairs)
        print(f"Tracked training usage for {len(pairs)} pairs")
    
    elif args.command == "track-api":
        if not args.pairs:
            print("Error: --pairs required")
            return 1
        
        for pair_str in args.pairs:
            card1, card2 = pair_str.split("|||")
            track_api_query(card1, card2, args.annotation_file)
        print(f"Tracked API queries for {len(args.pairs)} pairs")
    
    elif args.command == "track-graph":
        if not args.annotation_file:
            print("Error: --annotation-file required")
            return 1
        
        # Count pairs in annotation file
        annotations = load_similarity_annotations(args.annotation_file)
        pairs_count = len(annotations)
        
        track_graph_integration(args.annotation_file, pairs_count)
        print(f"Tracked graph integration for {pairs_count} pairs")

    return 0


if __name__ == "__main__":
    sys.exit(main())

