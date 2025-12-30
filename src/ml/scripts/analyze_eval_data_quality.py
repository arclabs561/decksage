#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
Analyze evaluation data quality and alignment with downstream uses.

Checks:
1. Format compatibility with evaluation scripts
2. Label quality (sufficient highly_relevant/relevant for MRR/MAP)
3. Query quality (not basic lands/common cards)
4. Coverage for downstream tasks (substitution, contextual discovery)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# Import filter sets
import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.utils.constants import get_filter_set, RELEVANCE_WEIGHTS
    HAS_CONSTANTS = True
except ImportError:
    HAS_CONSTANTS = False
    RELEVANCE_WEIGHTS = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }
    def get_filter_set(game: str, level: str = "basic") -> set:
        return set()


def analyze_test_set_quality(
    test_set_path: Path,
    game: str = "magic",
    pairs_csv: Path | None = None,
) -> dict[str, Any]:
    """Comprehensive quality analysis of test set."""
    with open(test_set_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", data) if isinstance(data, dict) else data
    
    # Get filter set for common cards
    filter_set = get_filter_set(game, level="all") if HAS_CONSTANTS else set()
    
    # Load pairs to check co-occurrence quality
    cooccurrence_data = {}
    if pairs_csv and pairs_csv.exists() and HAS_PANDAS:
        df = pd.read_csv(pairs_csv, nrows=100000)  # Sample
        for _, row in df.iterrows():
            card1 = str(row.get("NAME_1", "")).strip()
            card2 = str(row.get("NAME_2", "")).strip()
            count = int(row.get("COUNT_MULTISET", 1))
            if card1 and card2:
                if card1 not in cooccurrence_data:
                    cooccurrence_data[card1] = {}
                cooccurrence_data[card1][card2] = count
    
    analysis = {
        "total_queries": len(queries),
        "format_compatibility": {
            "has_version": "version" in data,
            "has_game": "game" in data,
            "has_queries": "queries" in data or isinstance(data, dict),
        },
        "query_quality": {
            "filtered_queries": 0,  # Queries that are common cards
            "queries_with_sufficient_labels": 0,  # >= 10 total labels
            "queries_with_highly_relevant": 0,  # Has highly_relevant
            "queries_with_relevant": 0,  # Has relevant
            "queries_for_mrr": 0,  # Has highly_relevant OR relevant (needed for MRR)
            "queries_for_substitution": 0,  # Has highly_relevant + relevant (for substitution task)
        },
        "label_distribution": {
            "highly_relevant": Counter(),
            "relevant": Counter(),
            "somewhat_relevant": Counter(),
            "marginally_relevant": Counter(),
        },
        "downstream_task_coverage": {
            "substitution_ready": 0,  # Queries with highly_relevant + relevant
            "contextual_discovery_ready": 0,  # Queries with metadata + expected synergies
        },
        "quality_issues": [],
    }
    
    for query, labels in queries.items():
        if not isinstance(labels, dict):
            continue
        
        # Check if query is filtered (common card)
        if query in filter_set:
            analysis["query_quality"]["filtered_queries"] += 1
            analysis["quality_issues"].append({
                "query": query,
                "issue": "filtered_common_card",
                "severity": "high",
            })
            continue
        
        # Count labels
        highly_rel = len(labels.get("highly_relevant", []))
        relevant = len(labels.get("relevant", []))
        somewhat_rel = len(labels.get("somewhat_relevant", []))
        marginally_rel = len(labels.get("marginally_relevant", []))
        total_labels = highly_rel + relevant + somewhat_rel + marginally_rel
        
        # Track distribution
        analysis["label_distribution"]["highly_relevant"][highly_rel] += 1
        analysis["label_distribution"]["relevant"][relevant] += 1
        analysis["label_distribution"]["somewhat_relevant"][somewhat_rel] += 1
        analysis["label_distribution"]["marginally_relevant"][marginally_rel] += 1
        
        # Quality checks
        if total_labels >= 10:
            analysis["query_quality"]["queries_with_sufficient_labels"] += 1
        
        if highly_rel > 0:
            analysis["query_quality"]["queries_with_highly_relevant"] += 1
        
        if relevant > 0:
            analysis["query_quality"]["queries_with_relevant"] += 1
        
        # MRR requires highly_relevant OR relevant
        if highly_rel > 0 or relevant > 0:
            analysis["query_quality"]["queries_for_mrr"] += 1
        else:
            analysis["quality_issues"].append({
                "query": query,
                "issue": "no_highly_relevant_or_relevant",
                "severity": "high",
                "detail": "MRR and MAP require at least highly_relevant or relevant labels",
            })
        
        # Substitution task needs highly_relevant + relevant
        if highly_rel > 0 and relevant > 0:
            analysis["query_quality"]["queries_for_substitution"] += 1
            analysis["downstream_task_coverage"]["substitution_ready"] += 1
        
        # Check label quality (co-occurrence validation)
        if pairs_csv and query in cooccurrence_data:
            query_cooccurrence = cooccurrence_data[query]
            highly_rel_cards = labels.get("highly_relevant", [])
            
            # Check if highly_relevant cards actually co-occur
            missing_cooccurrence = []
            for card in highly_rel_cards[:5]:  # Check top 5
                if card not in query_cooccurrence:
                    missing_cooccurrence.append(card)
            
            if len(missing_cooccurrence) > len(highly_rel_cards) * 0.5:  # >50% missing
                analysis["quality_issues"].append({
                    "query": query,
                    "issue": "low_cooccurrence_validation",
                    "severity": "medium",
                    "detail": f"{len(missing_cooccurrence)}/{len(highly_rel_cards)} highly_relevant cards don't co-occur",
                })
    
    # Convert Counter to dict for JSON serialization
    for key in analysis["label_distribution"]:
        analysis["label_distribution"][key] = dict(analysis["label_distribution"][key])
    
    return analysis


def print_analysis_report(analysis: dict[str, Any]) -> None:
    """Print human-readable analysis report."""
    print("=" * 70)
    print("EVALUATION DATA QUALITY ANALYSIS")
    print("=" * 70)
    
    print(f"\n📊 Summary")
    print(f"   Total queries: {analysis['total_queries']}")
    
    print(f"\n✅ Format Compatibility")
    fmt = analysis["format_compatibility"]
    print(f"   Has version: {fmt['has_version']}")
    print(f"   Has game: {fmt['has_game']}")
    print(f"   Has queries: {fmt['has_queries']}")
    
    print(f"\n📈 Query Quality")
    qq = analysis["query_quality"]
    print(f"   Filtered queries (common cards): {qq['filtered_queries']}")
    print(f"   Queries with 10+ labels: {qq['queries_with_sufficient_labels']}/{analysis['total_queries']}")
    print(f"   Queries with highly_relevant: {qq['queries_with_highly_relevant']}/{analysis['total_queries']}")
    print(f"   Queries with relevant: {qq['queries_with_relevant']}/{analysis['total_queries']}")
    print(f"   Queries usable for MRR/MAP: {qq['queries_for_mrr']}/{analysis['total_queries']}")
    print(f"   Queries usable for substitution: {qq['queries_for_substitution']}/{analysis['total_queries']}")
    
    print(f"\n📋 Label Distribution")
    for level, dist in analysis["label_distribution"].items():
        if dist:
            avg = sum(count * num for num, count in dist.items()) / sum(dist.values())
            print(f"   {level}: avg {avg:.1f} per query (range: {min(dist.keys())}-{max(dist.keys())})")
    
    print(f"\n🎯 Downstream Task Coverage")
    dtc = analysis["downstream_task_coverage"]
    print(f"   Substitution-ready: {dtc['substitution_ready']}/{analysis['total_queries']}")
    print(f"   Contextual discovery-ready: {dtc['contextual_discovery_ready']}/{analysis['total_queries']}")
    
    print(f"\n⚠️  Quality Issues")
    issues = analysis["quality_issues"]
    if not issues:
        print("   ✅ No issues found")
    else:
        high_severity = [i for i in issues if i.get("severity") == "high"]
        medium_severity = [i for i in issues if i.get("severity") == "medium"]
        
        print(f"   High severity: {len(high_severity)}")
        for issue in high_severity[:10]:
            print(f"      - {issue['query']}: {issue['issue']}")
            if "detail" in issue:
                print(f"        {issue['detail']}")
        
        if len(high_severity) > 10:
            print(f"      ... and {len(high_severity) - 10} more")
        
        print(f"   Medium severity: {len(medium_severity)}")
        for issue in medium_severity[:5]:
            print(f"      - {issue['query']}: {issue['issue']}")
        
        if len(medium_severity) > 5:
            print(f"      ... and {len(medium_severity) - 5} more")
    
    # Overall assessment
    print(f"\n{'=' * 70}")
    usable_for_mrr = qq['queries_for_mrr'] / analysis['total_queries'] if analysis['total_queries'] > 0 else 0
    usable_for_substitution = qq['queries_for_substitution'] / analysis['total_queries'] if analysis['total_queries'] > 0 else 0
    
    if usable_for_mrr >= 0.9 and usable_for_substitution >= 0.5 and qq['filtered_queries'] == 0:
        print("✅ QUALITY: EXCELLENT")
    elif usable_for_mrr >= 0.7 and usable_for_substitution >= 0.3:
        print("⚠️  QUALITY: GOOD (some issues)")
    else:
        print("❌ QUALITY: NEEDS IMPROVEMENT")
        print(f"   - {usable_for_mrr*100:.1f}% usable for MRR/MAP (target: 90%+)")
        print(f"   - {usable_for_substitution*100:.1f}% usable for substitution (target: 50%+)")
        print(f"   - {qq['filtered_queries']} filtered queries (target: 0)")


def main() -> int:
    """Analyze evaluation data quality."""
    parser = argparse.ArgumentParser(description="Analyze evaluation data quality")
    parser.add_argument("test_set", type=str, help="Path to test set JSON")
    parser.add_argument("--game", type=str, default="magic", help="Game name")
    parser.add_argument("--pairs-csv", type=str, help="Pairs CSV for co-occurrence validation")
    parser.add_argument("--output", type=str, help="Output JSON report")
    
    args = parser.parse_args()
    
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"Error: Test set not found: {test_set_path}")
        return 1
    
    pairs_csv = Path(args.pairs_csv) if args.pairs_csv else None
    
    print(f"Analyzing: {test_set_path}")
    if pairs_csv:
        print(f"Validating against: {pairs_csv}")
    print()
    
    analysis = analyze_test_set_quality(
        test_set_path=test_set_path,
        game=args.game,
        pairs_csv=pairs_csv,
    )
    
    print_analysis_report(analysis)
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\n📄 Full report saved to: {output_path}")
    
    # Return non-zero if quality is poor
    qq = analysis["query_quality"]
    usable_for_mrr = qq['queries_for_mrr'] / analysis['total_queries'] if analysis['total_queries'] > 0 else 0
    
    if usable_for_mrr < 0.7 or qq['filtered_queries'] > analysis['total_queries'] * 0.1:
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

