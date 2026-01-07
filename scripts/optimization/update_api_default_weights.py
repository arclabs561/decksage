#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Update API default weights from optimization results.

Reads best weights from grid search or learned methods and creates
a weights file that the API will automatically load.
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

from ml.utils.paths import PATHS


def main():
    parser = argparse.ArgumentParser(description="Update API default weights")
    parser.add_argument(
        "--source",
        type=str,
        choices=["grid_search", "learned"],
        default="grid_search",
        help="Source of weights (grid_search or learned)",
    )
    parser.add_argument(
        "--grid-search-file",
        type=str,
        default=str(PATHS.experiments / "grid_search_rrf_results.json"),
        help="Path to grid search results",
    )
    parser.add_argument(
        "--learned-file",
        type=str,
        help="Path to learned weights results (auto-detects if not specified)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PATHS.experiments / "optimized_fusion_weights_latest.json"),
        help="Output path for weights file",
    )
    
    args = parser.parse_args()
    
    # Load weights from source
    if args.source == "grid_search":
        weights_path = Path(args.grid_search_file)
        if not weights_path.exists():
            print(f"Error: Grid search file not found: {weights_path}")
            return 1
        
        with open(weights_path) as f:
            data = json.load(f)
        
        best_weights = data.get("best_weights", {})
        best_score = data.get("best_score", 0.0)
        
        print(f"Loaded from grid search:")
        print(f"  Best P@10: {best_score:.4f}")
        print(f"  Weights: {best_weights}")
        
    else:  # learned
        # Auto-detect learned file if not specified
        if args.learned_file:
            learned_path = Path(args.learned_file)
        else:
            # Find best learned weights file
            learned_files = list(PATHS.experiments.glob("learned_weights_*.json"))
            if not learned_files:
                print("Error: No learned weights files found")
                return 1
            
            # Load all and find best
            best_file = None
            best_score = -1.0
            for f in learned_files:
                try:
                    with open(f) as file:
                        d = json.load(file)
                    score = d.get("evaluation", {}).get("p_at_k", 0.0)
                    if score > best_score:
                        best_score = score
                        best_file = f
                except Exception:
                    continue
            
            if not best_file:
                print("Error: Could not find valid learned weights file")
                return 1
            
            learned_path = best_file
            print(f"Auto-selected best learned weights: {learned_path.name}")
        
        if not learned_path.exists():
            print(f"Error: Learned weights file not found: {learned_path}")
            return 1
        
        with open(learned_path) as f:
            data = json.load(f)
        
        best_weights = data.get("learned_weights", {})
        best_score = data.get("evaluation", {}).get("p_at_k", 0.0)
        method = data.get("method", "unknown")
        
        print(f"Loaded from learned method ({method}):")
        print(f"  Best P@10: {best_score:.4f}")
        print(f"  Weights: {best_weights}")
    
    # Create output in format expected by API
    output_data = {
        "best_weights": best_weights,
        "best_score": best_score,
        "source": args.source,
        "method": data.get("method", "grid_search") if args.source == "learned" else "grid_search",
    }
    
    # Write output
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nSaved weights to {output_path}")
    print(f"  API will automatically load these weights on next startup")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

