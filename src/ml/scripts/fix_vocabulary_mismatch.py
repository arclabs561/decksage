#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
Fix vocabulary mismatch between test set queries and embedding vocabulary.

Creates comprehensive name mapping by:
1. Loading all card names from training data
2. Normalizing names for fuzzy matching
3. Creating mappings for test set queries
4. Saving expanded name mapping
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

# Fix import path
import sys
from pathlib import Path as P
script_dir = P(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.utils.name_normalizer import NameMapper, normalize_card_name, find_name_matches


def load_training_vocabulary(pairs_csv: Path) -> set[str]:
    """Load all unique card names from training data."""
    if not HAS_PANDAS:
        print("❌ pandas required")
        return set()
    
    print(f"Loading vocabulary from {pairs_csv}...")
    df = pd.read_csv(pairs_csv)
    
    all_names = set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
    print(f"  Loaded {len(all_names):,} unique card names")
    
    return all_names


def create_name_mapping(
    test_queries: list[str],
    training_vocab: set[str],
    threshold: float = 0.85,
) -> dict[str, str]:
    """Create name mapping from test queries to training vocabulary."""
    mapping = {}
    matched = 0
    unmatched = []
    
    print(f"\nCreating name mappings (threshold={threshold})...")
    
    for query in test_queries:
        # Exact match
        if query in training_vocab:
            mapping[query] = query
            matched += 1
            continue
        
        # Normalized exact match
        query_norm = normalize_card_name(query)
        for train_name in training_vocab:
            train_norm = normalize_card_name(train_name)
            if query_norm == train_norm:
                mapping[query] = train_name
                matched += 1
                break
        else:
            # Fuzzy match
            matches = find_name_matches(query, list(training_vocab), threshold=threshold)
            if matches:
                best_match, score = matches[0]
                mapping[query] = best_match
                matched += 1
                print(f"  Fuzzy: '{query}' → '{best_match}' (score={score:.3f})")
            else:
                unmatched.append(query)
    
    print(f"\n✅ Mapped {matched}/{len(test_queries)} queries")
    if unmatched:
        print(f"⚠️  {len(unmatched)} queries unmatched:")
        for q in unmatched[:10]:
            print(f"     {q}")
        if len(unmatched) > 10:
            print(f"     ... and {len(unmatched) - 10} more")
    
    return mapping


def main() -> int:
    """Fix vocabulary mismatch."""
    parser = argparse.ArgumentParser(description="Fix vocabulary mismatch")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--pairs-csv", type=str, required=True, help="Training pairs CSV")
    parser.add_argument("--name-mapping", type=str, required=True, help="Output name mapping JSON")
    parser.add_argument("--threshold", type=float, default=0.85, help="Fuzzy match threshold")
    
    args = parser.parse_args()
    
    if not HAS_PANDAS:
        print("❌ pandas required")
        return 1
    
    # Load test set queries
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"❌ Test set not found: {test_set_path}")
        return 1
    
    with open(test_set_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", data) if isinstance(data, dict) else data
    test_queries = list(queries.keys())
    
    print(f"📊 Loaded {len(test_queries)} test queries")
    
    # Load training vocabulary
    pairs_path = Path(args.pairs_csv)
    if not pairs_path.exists():
        print(f"❌ Pairs CSV not found: {pairs_path}")
        return 1
    
    training_vocab = load_training_vocabulary(pairs_path)
    
    # Create mapping
    mapping = create_name_mapping(test_queries, training_vocab, threshold=args.threshold)
    
    # Load existing mapping if it exists
    mapping_path = Path(args.name_mapping)
    existing_mapping = {}
    if mapping_path.exists():
        with open(mapping_path) as f:
            existing_data = json.load(f)
            existing_mapping = existing_data.get("mapping", {})
    
    # Merge mappings (new takes precedence)
    merged_mapping = {**existing_mapping, **mapping}
    
    # Save
    output_data = {
        "mapping": merged_mapping,
        "metadata": {
            "total_mappings": len(merged_mapping),
            "new_mappings": len(mapping),
            "test_set": str(test_set_path),
            "pairs_csv": str(pairs_path),
        }
    }
    
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n✅ Saved {len(merged_mapping)} mappings to {mapping_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

