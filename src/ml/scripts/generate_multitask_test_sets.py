#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
# ]
# ///
"""
Generate multi-task test sets.

Creates separate test sets for each task:
1. Co-occurrence test set (from pairs CSV)
2. Functional similarity test set (from canonical test set)
3. Substitution test set (from substitution pairs)

Then combines into multi-task evaluation format.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def generate_cooccurrence_test_set(
    pairs_df: pd.DataFrame,
    min_cooccurrence: int = 5,
    max_queries: int = 50,
) -> dict[str, dict[str, Any]]:
    """Generate co-occurrence test set from pairs."""
    if not HAS_PANDAS:
        return {}
    
    # Count co-occurrences per card
    cooccurrence = defaultdict(list)
    
    for _, row in pairs_df.iterrows():
        n1 = row.get("NAME_1", "")
        n2 = row.get("NAME_2", "")
        count = row.get("COUNT_MULTISET", 1)
        
        if n1 and n2 and count >= min_cooccurrence:
            cooccurrence[n1].append((n2, count))
            cooccurrence[n2].append((n1, count))
    
    # Select top cards by degree
    card_degrees = {card: len(pairs) for card, pairs in cooccurrence.items()}
    top_cards = sorted(card_degrees.items(), key=lambda x: x[1], reverse=True)[:max_queries]
    
    test_set = {}
    
    for query_card, _ in top_cards:
        # Get top co-occurring cards
        cooccurring = sorted(cooccurrence[query_card], key=lambda x: x[1], reverse=True)
        
        if len(cooccurring) >= 3:
            test_set[query_card] = {
                "task": "cooccurrence",
                "highly_relevant": [card for card, count in cooccurring[:5]],
                "relevant": [card for card, count in cooccurring[5:10]],
                "somewhat_relevant": [card for card, count in cooccurring[10:15]],
                "marginally_relevant": [],
                "irrelevant": [],
            }
    
    return test_set


def extract_functional_similarity_test_set(
    canonical_test_set: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Extract functional similarity queries from canonical test set."""
    functional = {}
    
    for query, labels in canonical_test_set.items():
        # Canonical test set is already functional similarity
        functional[query] = {
            "task": "functional_similarity",
            **labels,
        }
    
    return functional


def extract_substitution_test_set(
    substitution_pairs: list[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """Create substitution test set from pairs."""
    # Group by original card
    substitution_groups = defaultdict(list)
    
    for original, substitute in substitution_pairs:
        substitution_groups[original].append(substitute)
    
    test_set = {}
    
    for original, substitutes in substitution_groups.items():
        if len(substitutes) >= 1:
            test_set[original] = {
                "task": "substitution",
                "highly_relevant": substitutes[:5],
                "relevant": substitutes[5:10] if len(substitutes) > 10 else [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }
    
    return test_set


def main() -> int:
    """Generate multi-task test sets."""
    parser = argparse.ArgumentParser(description="Generate multi-task test sets")
    parser.add_argument("--pairs", type=Path, required=True, help="Pairs CSV for co-occurrence")
    parser.add_argument("--canonical-test-set", type=Path, help="Canonical test set for functional similarity")
    parser.add_argument("--substitution-pairs", type=Path, help="Substitution pairs JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output multi-task test set JSON")
    
    args = parser.parse_args()
    
    if not HAS_PANDAS:
        print("Error: pandas required")
        return 1
    
    print("Generating multi-task test sets...")
    
    test_sets = {
        "cooccurrence": {},
        "functional_similarity": {},
        "substitution": {},
    }
    
    # 1. Co-occurrence test set
    if args.pairs.exists():
        print(f"\n1. Generating co-occurrence test set from {args.pairs}...")
        pairs_df = pd.read_csv(args.pairs, nrows=100000)  # Sample
        cooccurrence = generate_cooccurrence_test_set(pairs_df)
        test_sets["cooccurrence"] = cooccurrence
        print(f"   Generated {len(cooccurrence)} queries")
    
    # 2. Functional similarity test set
    if args.canonical_test_set and args.canonical_test_set.exists():
        print(f"\n2. Extracting functional similarity test set from {args.canonical_test_set}...")
        with open(args.canonical_test_set) as f:
            canonical = json.load(f)
        functional = extract_functional_similarity_test_set(canonical.get("queries", canonical))
        test_sets["functional_similarity"] = functional
        print(f"   Extracted {len(functional)} queries")
    
    # 3. Substitution test set
    if args.substitution_pairs and args.substitution_pairs.exists():
        print(f"\n3. Creating substitution test set from {args.substitution_pairs}...")
        with open(args.substitution_pairs) as f:
            sub_data = json.load(f)
        if isinstance(sub_data, list):
            substitution_pairs = [tuple(pair) for pair in sub_data]
        else:
            substitution_pairs = []
        substitution = extract_substitution_test_set(substitution_pairs)
        test_sets["substitution"] = substitution
        print(f"   Created {len(substitution)} queries")
    
    # Combine into unified format
    output_data = {
        "version": "multitask",
        "tasks": {
            "cooccurrence": {
                "num_queries": len(test_sets["cooccurrence"]),
                "queries": test_sets["cooccurrence"],
            },
            "functional_similarity": {
                "num_queries": len(test_sets["functional_similarity"]),
                "queries": test_sets["functional_similarity"],
            },
            "substitution": {
                "num_queries": len(test_sets["substitution"]),
                "queries": test_sets["substitution"],
            },
        },
    }
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n✅ Multi-task test set saved to {args.output}")
    print(f"\nSummary:")
    print(f"  Co-occurrence: {len(test_sets['cooccurrence'])} queries")
    print(f"  Functional similarity: {len(test_sets['functional_similarity'])} queries")
    print(f"  Substitution: {len(test_sets['substitution'])} queries")
    print(f"  Total: {sum(len(q) for q in test_sets.values())} queries")
    
    return 0


if __name__ == "__main__":
    exit(main())

