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
    PATHS = type('PATHS', (), {
        'embeddings': PROJECT_ROOT / "data" / "embeddings",
        'experiments': PROJECT_ROOT / "experiments",
        'test_magic': PROJECT_ROOT / "experiments" / "test_set_unified_magic.json",
    })()


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
        "hybrid": PATHS.hybrid_evaluation_results if HAS_PATHS else Path("experiments/hybrid_evaluation_results.json"),
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


def main() -> int:
    """Main monitoring loop."""
    parser = argparse.ArgumentParser(description="Comprehensive system monitoring")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
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

