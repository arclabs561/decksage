#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
View and query evaluation logs.

Supports:
- Viewing recent runs
- Querying by method, evaluation type, date range
- Comparing runs
- Exporting results
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.utils.evaluation_logger import EvaluationLogger


def main():
    parser = argparse.ArgumentParser(description="View and query evaluation logs")
    parser.add_argument(
        "--recent",
        type=int,
        default=10,
        help="Show N most recent runs (default: 10)",
    )
    parser.add_argument(
        "--type",
        type=str,
        help="Filter by evaluation type (e.g., 'ndcg_evaluation', 'fusion_comparison')",
    )
    parser.add_argument(
        "--method",
        type=str,
        help="Filter by method (e.g., 'fusion_rrf', 'embedding')",
    )
    parser.add_argument(
        "--min-p-at-k",
        type=float,
        help="Minimum P@K value",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        help="Start date (ISO format: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        help="End date (ISO format: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["table", "json", "detailed"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Get specific run by ID",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export results to JSON file",
    )
    
    args = parser.parse_args()
    
    logger = EvaluationLogger()
    
    # Get specific run
    if args.run_id:
        run = logger.get_run_by_id(args.run_id)
        if not run:
            print(f"Run ID '{args.run_id}' not found")
            return 1
        
        if args.format == "json":
            print(json.dumps(run, indent=2))
        else:
            print("=" * 80)
            print(f"Evaluation Run: {args.run_id}")
            print("=" * 80)
            print(f"Timestamp: {run.get('timestamp')}")
            print(f"Type: {run.get('evaluation_type')}")
            print(f"Method: {run.get('method')}")
            print(f"Test Set: {run.get('test_set_path')}")
            print(f"Queries: {run.get('num_queries')}")
            print("")
            print("Metrics:")
            metrics = run.get("metrics", {})
            for key, value in metrics.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")
            print("")
            if run.get("config"):
                print("Config:")
                config = run.get("config", {})
                for key, value in config.items():
                    print(f"  {key}: {value}")
                print("")
            if run.get("notes"):
                print(f"Notes: {run.get('notes')}")
        
        return 0
    
    # Query runs
    runs = logger.query_runs(
        evaluation_type=args.type,
        method=args.method,
        min_p_at_k=args.min_p_at_k,
        date_from=args.from_date,
        date_to=args.to_date,
    )
    
    # Limit to recent if not filtering
    if not any([args.type, args.method, args.min_p_at_k, args.from_date, args.to_date]):
        runs = runs[:args.recent]
    
    if not runs:
        print("No evaluation runs found matching criteria")
        return 0
    
    # Export if requested
    if args.export:
        with open(args.export, "w") as f:
            json.dump(runs, f, indent=2)
        print(f"Exported {len(runs)} runs to {args.export}")
        return 0
    
    # Display results
    if args.format == "json":
        print(json.dumps(runs, indent=2))
    elif args.format == "detailed":
        for run in runs:
            print("=" * 80)
            print(f"Run ID: {run.get('run_id')}")
            print(f"Timestamp: {run.get('timestamp')}")
            print(f"Type: {run.get('evaluation_type')}")
            print(f"Method: {run.get('method')}")
            print(f"Queries: {run.get('num_queries')}")
            print("Metrics:")
            metrics = run.get("metrics", {})
            for key, value in metrics.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")
            print("")
    else:  # table
        print(f"{'Run ID':<30} {'Type':<20} {'Method':<15} {'P@10':<10} {'NDCG@10':<10} {'Queries':<10}")
        print("-" * 100)
        
        for run in runs:
            run_id = run.get("run_id", "")[:30]
            eval_type = run.get("evaluation_type", "")[:20]
            method = run.get("method", "")[:15]
            metrics = run.get("metrics", {})
            p_at_k = metrics.get("p_at_k") or metrics.get("p_at_10", 0.0)
            ndcg = metrics.get("ndcg_at_k") or metrics.get("ndcg_at_10", 0.0)
            num_queries = run.get("num_queries") or 0
            
            print(
                f"{run_id:<30} "
                f"{eval_type:<20} "
                f"{method:<15} "
                f"{p_at_k:<10.4f} "
                f"{ndcg:<10.4f} "
                f"{num_queries:<10}"
            )
        
        print("")
        print(f"Total: {len(runs)} runs")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

