#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Deep data integrity checks.

Checks for:
- Data corruption
- Inconsistencies
- Missing required fields
- Invalid values
- Duplicate entries
- Referential integrity
"""

import json
import sys
from pathlib import Path
from typing import Any
from collections import Counter

# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def check_test_set_integrity(test_set_path: Path) -> dict[str, Any]:
    """Deep integrity check for test set."""
    issues = []
    stats = {}
    
    try:
        with open(test_set_path) as f:
            data = json.load(f)
        
        queries = data.get("queries", data)
        if not isinstance(queries, dict):
            return {
                "valid": False,
                "error": "Invalid format: queries not a dict",
            }
        
        stats["total_queries"] = len(queries)
        
        # Check for duplicate queries
        query_names = list(queries.keys())
        duplicates = [q for q, count in Counter(query_names).items() if count > 1]
        if duplicates:
            issues.append({
                "type": "duplicate_queries",
                "queries": duplicates,
                "severity": "high",
            })
        
        # Check each query
        empty_labels = []
        invalid_labels = []
        duplicate_labels = []
        
        for query, labels in queries.items():
            if not isinstance(labels, dict):
                issues.append({
                    "type": "invalid_label_format",
                    "query": query,
                    "severity": "high",
                })
                continue
            
            # Check for empty label lists
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
                level_labels = labels.get(level, [])
                if not isinstance(level_labels, list):
                    invalid_labels.append((query, level))
                elif len(level_labels) == 0:
                    # Empty is OK, but track it
                    pass
                else:
                    # Check for duplicates within level
                    if len(level_labels) != len(set(level_labels)):
                        duplicate_labels.append((query, level))
            
            # Check for cards appearing in multiple relevance levels
            all_cards = []
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
                all_cards.extend(labels.get(level, []))
            
            card_counts = Counter(all_cards)
            multi_level_cards = [card for card, count in card_counts.items() if count > 1]
            if multi_level_cards:
                issues.append({
                    "type": "card_in_multiple_levels",
                    "query": query,
                    "cards": multi_level_cards,
                    "severity": "medium",
                })
        
        if empty_labels:
            issues.append({
                "type": "empty_label_lists",
                "count": len(empty_labels),
                "severity": "low",
            })
        
        if invalid_labels:
            issues.append({
                "type": "invalid_label_format",
                "count": len(invalid_labels),
                "examples": invalid_labels[:5],
                "severity": "high",
            })
        
        if duplicate_labels:
            issues.append({
                "type": "duplicate_labels_in_level",
                "count": len(duplicate_labels),
                "examples": duplicate_labels[:5],
                "severity": "medium",
            })
        
        return {
            "valid": len(issues) == 0,
            "test_set": str(test_set_path),
            "stats": stats,
            "issues": issues,
        }
    
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"Invalid JSON: {e}",
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


def check_evaluation_results_integrity(results_path: Path) -> dict[str, Any]:
    """Deep integrity check for evaluation results."""
    issues = []
    
    try:
        with open(results_path) as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return {
                "valid": False,
                "error": "Invalid format: not a dict",
            }
        
        results = data.get("results", {})
        if not isinstance(results, dict):
            return {
                "valid": False,
                "error": "Invalid format: results not a dict",
            }
        
        # Check for consistency
        test_set_path = data.get("test_set")
        if test_set_path:
            test_set_file = Path(test_set_path)
            if test_set_file.exists():
                with open(test_set_file) as f:
                    test_data = json.load(f)
                test_queries = test_data.get("queries", test_data)
                expected_queries = len(test_queries) if isinstance(test_queries, dict) else 0
            else:
                expected_queries = None
        else:
            expected_queries = None
        
        # Check each result
        inconsistent_results = []
        for method_name, result in results.items():
            if not isinstance(result, dict):
                issues.append({
                    "type": "invalid_result_format",
                    "method": method_name,
                    "severity": "high",
                })
                continue
            
            num_queries = result.get("num_queries", 0)
            num_evaluated = result.get("num_evaluated", 0)
            
            # Check consistency
            if expected_queries and num_queries != expected_queries:
                inconsistent_results.append({
                    "method": method_name,
                    "expected": expected_queries,
                    "actual": num_queries,
                })
            
            # Check for impossible values
            if num_evaluated > num_queries:
                issues.append({
                    "type": "impossible_value",
                    "method": method_name,
                    "issue": f"num_evaluated ({num_evaluated}) > num_queries ({num_queries})",
                    "severity": "high",
                })
            
            # Check metric ranges
            p_at_10 = result.get("p@10", 0)
            if p_at_10 < 0 or p_at_10 > 1:
                issues.append({
                    "type": "invalid_metric_value",
                    "method": method_name,
                    "metric": "p@10",
                    "value": p_at_10,
                    "severity": "high",
                })
        
        if inconsistent_results:
            issues.append({
                "type": "inconsistent_query_counts",
                "count": len(inconsistent_results),
                "examples": inconsistent_results[:5],
                "severity": "medium",
            })
        
        return {
            "valid": len(issues) == 0,
            "results_file": str(results_path),
            "issues": issues,
        }
    
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deep data integrity checks")
    parser.add_argument(
        "--test-set",
        type=Path,
        action="append",
        help="Test set to check",
    )
    parser.add_argument(
        "--results",
        type=Path,
        action="append",
        help="Evaluation results to check",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )
    
    args = parser.parse_args()
    
    if not args.test_set and not args.results:
        # Default: check all test sets and results
        args.test_set = [
            Path("experiments/test_set_canonical_magic.json"),
            Path("experiments/test_set_unified_magic.json"),
            Path("experiments/test_set_canonical_magic_improved.json"),
        ]
        args.results = [
            Path("experiments/evaluation_results.json"),
        ]
    
    print("Deep Data Integrity Checks")
    print("=" * 70)
    print()
    
    all_results = {}
    
    # Check test sets
    if args.test_set:
        print("Checking test sets...")
        for test_set_path in args.test_set:
            if not test_set_path.exists():
                print(f"  ⚠ {test_set_path.name}: not found")
                continue
            
            print(f"  Checking {test_set_path.name}...", end=" ", flush=True)
            result = check_test_set_integrity(test_set_path)
            all_results[f"test_set_{test_set_path.stem}"] = result
            
            if result.get("valid"):
                print("✓")
            else:
                print(f"✗ {len(result.get('issues', []))} issues")
        print()
    
    # Check evaluation results
    if args.results:
        print("Checking evaluation results...")
        for results_path in args.results:
            if not results_path.exists():
                print(f"  ⚠ {results_path.name}: not found")
                continue
            
            print(f"  Checking {results_path.name}...", end=" ", flush=True)
            result = check_evaluation_results_integrity(results_path)
            all_results[f"results_{results_path.stem}"] = result
            
            if result.get("valid"):
                print("✓")
            else:
                print(f"✗ {len(result.get('issues', []))} issues")
        print()
    
    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    total_issues = 0
    for name, result in all_results.items():
        issues = result.get("issues", [])
        if issues:
            print(f"\n{name}:")
            for issue in issues[:5]:
                severity = issue.get("severity", "unknown")
                issue_type = issue.get("type", "unknown")
                print(f"  [{severity.upper()}] {issue_type}")
                if "query" in issue:
                    print(f"      Query: {issue['query']}")
                if "method" in issue:
                    print(f"      Method: {issue['method']}")
            if len(issues) > 5:
                print(f"  ... and {len(issues) - 5} more issues")
            total_issues += len(issues)
    
    if total_issues == 0:
        print("\n✓ No integrity issues found")
    else:
        print(f"\n⚠ Found {total_issues} integrity issues")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({
                "summary": {
                    "total_issues": total_issues,
                },
                "results": all_results,
            }, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

