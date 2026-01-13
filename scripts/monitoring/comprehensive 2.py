#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Comprehensive monitoring of all system components.
Combines: monitor_comprehensive.py, monitor_progress.py, monitor_completion.py, monitor_until_completion.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


# Set up paths
_script_file = Path(__file__).resolve()
_src_dir = _script_file.parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

try:
    from ml.utils.paths import PATHS

    HAS_PATHS = True
except ImportError:
    HAS_PATHS = False
    # Fallback paths
    PROJECT_ROOT = _script_file.parent.parent.parent
    PATHS = type(
        "PATHS",
        (),
        {
            "embeddings": PROJECT_ROOT / "data" / "embeddings",
            "experiments": PROJECT_ROOT / "experiments",
            "test_magic": PROJECT_ROOT / "experiments" / "test_set_unified_magic.json",
        },
    )()


def check_embeddings() -> dict[str, dict]:
    """Check embedding training status."""
    results = {}
    embeddings = {
        "gnn": PATHS.embeddings / "gnn_graphsage.json",
        "cooccurrence": PATHS.embeddings / "production.wv",
    }

    for name, path in embeddings.items():
        if path.exists():
            mtime = path.stat().st_mtime
            age_min = (time.time() - mtime) / 60
            size_mb = path.stat().st_size / (1024 * 1024)
            results[name] = {
                "exists": True,
                "size_mb": size_mb,
                "age_min": age_min,
                "status": "recent" if age_min < 10 else "complete",
            }
        else:
            results[name] = {
                "exists": False,
                "status": "missing",
            }
    return results


def check_pipeline_health() -> dict[str, Any]:
    """Check pipeline health using agentic validation tools."""
    try:
        from ml.qa.agentic_qa_tools import GraphQATools

        tools = GraphQATools()
        summary = tools.get_pipeline_summary()
        integrity = tools.check_data_integrity()
        stats = tools.check_graph_statistics()

        tools.close()

        return {
            "pipeline": {
                "orders_with_data": summary.get("orders_with_data", 0),
                "orders_with_issues": summary.get("orders_with_issues", 0),
                "total_orders": summary.get("total_orders", 7),
            },
            "integrity": {
                "score": integrity.get("integrity_score", 0),
                "orphaned_edges": integrity.get("orphaned_edges", 0),
            },
            "graph": {
                "nodes": stats.get("nodes", {}).get("total", 0),
                "edges": stats.get("edges", {}).get("total", 0),
            },
        }
    except Exception as e:
        return {"error": str(e), "status": "unavailable"}


def check_test_sets() -> dict[str, dict]:
    """Check test set status."""
    results = {}
    test_sets = {
        "magic": PATHS.test_magic if HAS_PATHS else Path("experiments/test_set_unified_magic.json"),
    }

    for game, path in test_sets.items():
        if path.exists():
            mtime = path.stat().st_mtime
            age_min = (time.time() - mtime) / 60
            try:
                with open(path) as f:
                    data = json.load(f)
                queries = data.get("queries", data)
                size = len(queries) if isinstance(queries, dict) else len(queries)
                results[game] = {
                    "exists": True,
                    "size": size,
                    "age_min": age_min,
                    "status": "recent" if age_min < 10 else "stable",
                }
            except Exception:
                results[game] = {"exists": True, "status": "error"}
        else:
            results[game] = {"exists": False, "status": "missing"}
    return results


def check_evaluation_results() -> dict[str, dict]:
    """Check evaluation results."""
    results = {}
    eval_files = {
        "hybrid": PATHS.hybrid_evaluation_results
        if HAS_PATHS
        else Path("experiments/hybrid_evaluation_results.json"),
    }

    for name, path in eval_files.items():
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    p_at_10 = data.get("p@10", 0.0)
                    results[name] = {
                        "exists": True,
                        "p@10": p_at_10,
                        "status": "complete",
                    }
                else:
                    results[name] = {"exists": True, "status": "found"}
            except Exception:
                results[name] = {"exists": True, "status": "error"}
        else:
            results[name] = {"exists": False, "status": "missing"}
    return results


def monitor_once() -> None:
    """Run one monitoring check."""
    print("=" * 70)
    print("COMPREHENSIVE MONITOR")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Embeddings
    print("EMBEDDINGS:")
    emb_results = check_embeddings()
    for name, info in emb_results.items():
        if info["exists"]:
            status = "✓" if info["status"] == "recent" else "✓"
            size = info.get("size_mb", 0)
            age = info.get("age_min", 0)
            print(f"  {status} {name}: {size:.1f} MB ({age:.1f} min ago)")
        else:
            print(f"  ⏳ {name}: Missing")
    print()

    # Test sets
    print("TEST SETS:")
    test_results = check_test_sets()
    for game, info in test_results.items():
        if info["exists"]:
            status = "✓" if info["status"] == "recent" else "✓"
            size = info.get("size", 0)
            age = info.get("age_min", 0)
            print(f"  {status} {game}: {size} queries ({age:.1f} min ago)")
        else:
            print(f"  ⏳ {game}: Missing")
    print()

    # Evaluation
    print("EVALUATION:")
    eval_results = check_evaluation_results()
    for name, info in eval_results.items():
        if info["exists"]:
            p_at_10 = info.get("p@10", None)
            if p_at_10 is not None:
                print(f"  ✓ {name}: P@10={p_at_10:.3f}")
            else:
                print(f"  ✓ {name}: Found")
        else:
            print(f"  ⏳ {name}: Missing")
    print()

    # Pipeline Health
    print("PIPELINE HEALTH:")
    pipeline_health = check_pipeline_health()
    if "error" not in pipeline_health:
        pipeline = pipeline_health.get("pipeline", {})
        integrity = pipeline_health.get("integrity", {})
        graph = pipeline_health.get("graph", {})

        orders_ok = pipeline.get("orders_with_data", 0)
        orders_issues = pipeline.get("orders_with_issues", 0)
        total = pipeline.get("total_orders", 7)

        if orders_issues == 0:
            print(f"  ✓ Pipeline: {orders_ok}/{total} orders healthy")
        else:
            print(f"  ⚠ Pipeline: {orders_ok}/{total} orders healthy, {orders_issues} with issues")

        integrity_score = integrity.get("score", 0)
        orphaned = integrity.get("orphaned_edges", 0)
        if integrity_score >= 0.95 and orphaned == 0:
            print(f"  ✓ Graph integrity: {integrity_score:.1%}")
        else:
            print(f"  ⚠ Graph integrity: {integrity_score:.1%} ({orphaned} orphaned edges)")

        print(f"  ✓ Graph: {graph.get('nodes', 0):,} nodes, {graph.get('edges', 0):,} edges")
    else:
        print(f"  ⚠ Pipeline health check unavailable: {pipeline_health.get('error', 'unknown')}")
    print()


def main() -> int:
    """Main monitoring loop."""
    parser = argparse.ArgumentParser(description="Comprehensive system monitoring")
    parser.add_argument(
        "--interval", type=int, default=60, help="Check interval in seconds (default: 60)"
    )
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()

    if args.once:
        monitor_once()
        return 0

    iteration = 0
    try:
        while True:
            iteration += 1
            if iteration > 1:
                print()
            monitor_once()
            print(f"Next check in {args.interval}s...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
