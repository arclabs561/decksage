#!/usr/bin/env python3
"""
Set up multi-judge annotation pipeline.

Configures and runs multiple LLM judges with different models, prompts, and parameters.
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.scripts.parallel_multi_judge import generate_labels_parallel
    from ml.experimental.multi_perspective_judge import MultiPerspectiveJudge
    HAS_MULTI_JUDGE = True
except ImportError as e:
    HAS_MULTI_JUDGE = False
    print(f"Warning: Multi-judge tools not available: {e}")


# Judge configurations
# Using Gemini 3 Flash (primary) and Claude 4.5 (fallback) for judging
# Gemini 3 Flash: 3x faster, 83% cheaper, 71.3 Intelligence Index, 1M+ token context
# Claude 4.5: Better for sustained reasoning, planning consistency
JUDGE_CONFIGS = [
    {
        "name": "competitive",
        "model": "google/gemini-3-flash-preview",  # Fast, high quality
        "perspective": "competitive",
        "temperature": 0.3,
        "description": "Competitive tournament player perspective",
    },
    {
        "name": "budget",
        "model": "google/gemini-3-flash-preview",  # Cost-effective
        "perspective": "budget",
        "temperature": 0.3,
        "description": "Budget-conscious player perspective",
    },
    {
        "name": "rules_expert",
        "model": "anthropic/claude-sonnet-4-5",  # Better for detailed reasoning
        "perspective": "rules",
        "temperature": 0.2,
        "description": "Rules expert perspective",
    },
    {
        "name": "meta_analyst",
        "model": "anthropic/claude-sonnet-4-5",  # Better for complex analysis
        "perspective": "meta",
        "temperature": 0.4,
        "description": "Metagame analyst perspective",
    },
]


def run_parallel_multi_judge(
    query: str,
    candidates: list[str],
    num_judges: int = 3,
    game: str | None = None,
) -> dict[str, Any]:
    """Run parallel multi-judge labeling."""
    if not HAS_MULTI_JUDGE:
        print("Error: Multi-judge tools not available")
        return {}
    
    print(f"Running parallel multi-judge for: {query}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Judges: {num_judges}")
    
    result = generate_labels_parallel(
        query,
        num_judges=num_judges,
        game=game,
        max_workers=num_judges,
        timeout=120.0,
    )
    
    return result


def run_multi_perspective_judge(
    query: str,
    candidates: list[str],
    perspectives: list[str] | None = None,
) -> dict[str, Any]:
    """Run multi-perspective judge."""
    if not HAS_MULTI_JUDGE:
        print("Error: Multi-perspective judge not available")
        return {}
    
    print(f"Running multi-perspective judge for: {query}")
    
    judge = MultiPerspectiveJudge()
    
    if perspectives is None:
        perspectives = ["competitive", "rules", "meta"]
    
    result = judge.judge_multi_perspective(query, candidates, perspectives)
    
    # Save as annotations
    output_dir = project_root / "annotations"
    saved_file = judge.save_judgment_batch(result, str(output_dir))
    
    print(f"✓ Saved multi-perspective judgment: {saved_file}")
    
    return result


def setup_pipeline_for_queries(
    queries: list[dict[str, Any]],
    method: str = "parallel",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Set up multi-judge pipeline for multiple queries."""
    output_dir = output_dir or project_root / "annotations"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "queries_processed": 0,
        "annotations_created": 0,
        "results": [],
    }
    
    for i, query_data in enumerate(queries, 1):
        query = query_data.get("query", "")
        candidates = query_data.get("candidates", [])
        
        if not query or not candidates:
            continue
        
        print(f"\n[{i}/{len(queries)}] Processing: {query}")
        
        try:
            if method == "parallel":
                result = run_parallel_multi_judge(query, candidates)
            elif method == "perspective":
                result = run_multi_perspective_judge(query, candidates)
            else:
                print(f"Unknown method: {method}")
                continue
            
            if result:
                results["queries_processed"] += 1
                results["results"].append({
                    "query": query,
                    "result": result,
                })
        
        except Exception as e:
            print(f"Error processing {query}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save summary
    summary_file = output_dir / f"multi_judge_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Pipeline complete: {summary_file}")
    print(f"  Queries processed: {results['queries_processed']}")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Set up multi-judge annotation pipeline"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Single query card to judge",
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        help="Candidate cards for single query",
    )
    parser.add_argument(
        "--batch-file",
        type=Path,
        help="YAML batch file with queries and candidates",
    )
    parser.add_argument(
        "--method",
        choices=["parallel", "perspective"],
        default="parallel",
        help="Multi-judge method",
    )
    parser.add_argument(
        "--num-judges",
        type=int,
        default=3,
        help="Number of parallel judges (for parallel method)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "annotations",
        help="Output directory",
    )
    
    args = parser.parse_args()
    
    if not HAS_MULTI_JUDGE:
        print("Error: Multi-judge tools not available")
        print("Install dependencies and check imports")
        return 1
    
    if args.query and args.candidates:
        # Single query
        if args.method == "parallel":
            result = run_parallel_multi_judge(args.query, args.candidates, args.num_judges)
        else:
            result = run_multi_perspective_judge(args.query, args.candidates)
        
        print(f"\nResult: {json.dumps(result, indent=2)}")
    
    elif args.batch_file:
        # Batch processing
        import yaml
        with open(args.batch_file) as f:
            data = yaml.safe_load(f)
        
        queries = []
        for task in data.get("tasks", []):
            query = task.get("query", "")
            candidates = [c.get("card", "") for c in task.get("candidates", [])]
            if query and candidates:
                queries.append({"query": query, "candidates": candidates})
        
        setup_pipeline_for_queries(queries, args.method, args.output_dir)
    
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


