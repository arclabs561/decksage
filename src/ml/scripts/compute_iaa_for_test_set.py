#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Compute Inter-Annotator Agreement (IAA) for test set labels.

Analyzes label quality and identifies queries with low agreement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from ml.evaluation.inter_annotator_agreement import InterAnnotatorAgreement
    HAS_IAA = True
except ImportError:
    HAS_IAA = False
    print("IAA module not available")


def analyze_test_set_iaa(test_set_path: Path) -> dict[str, Any]:
    """Analyze IAA for test set."""
    with open(test_set_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", data) if isinstance(data, dict) else data
    
    results = {
        "total_queries": len(queries),
        "queries_with_iaa": 0,
        "queries_with_low_agreement": [],
        "avg_agreement": 0.0,
        "iaa_details": {},
    }
    
    agreement_scores = []
    
    for query_name, query_data in queries.items():
        if not isinstance(query_data, dict):
            continue
        
        iaa_data = query_data.get("iaa", {})
        if not iaa_data:
            continue
        
        results["queries_with_iaa"] += 1
        agreement = iaa_data.get("agreement_rate", 0.0)
        agreement_scores.append(agreement)
        
        results["iaa_details"][query_name] = {
            "agreement_rate": agreement,
            "num_judges": iaa_data.get("num_judges", 0),
            "num_cards": iaa_data.get("num_cards", 0),
        }
        
        # Flag low agreement (< 0.6)
        if agreement < 0.6:
            results["queries_with_low_agreement"].append({
                "query": query_name,
                "agreement": agreement,
            })
    
    if agreement_scores:
        results["avg_agreement"] = sum(agreement_scores) / len(agreement_scores)
    
    return results


def main() -> int:
    """Compute IAA for test set."""
    parser = argparse.ArgumentParser(description="Compute IAA for test set")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--output", type=str, help="Output JSON (optional)")
    
    args = parser.parse_args()
    
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"❌ Test set not found: {test_set_path}")
        return 1
    
    print("Computing IAA for test set...")
    results = analyze_test_set_iaa(test_set_path)
    
    print("\n=== IAA Analysis ===")
    print(f"Total queries: {results['total_queries']}")
    print(f"Queries with IAA data: {results['queries_with_iaa']}")
    print(f"Average agreement: {results['avg_agreement']:.3f}")
    print(f"Queries with low agreement (<0.6): {len(results['queries_with_low_agreement'])}")
    
    if results['queries_with_low_agreement']:
        print("\n⚠️  Queries needing re-labeling:")
        for item in results['queries_with_low_agreement']:
            print(f"  - {item['query']}: {item['agreement']:.3f}")
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Results saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

