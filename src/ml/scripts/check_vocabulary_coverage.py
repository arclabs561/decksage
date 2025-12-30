#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Check vocabulary coverage between test set and embeddings.

Identifies which queries are missing and suggests fixes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# Fix import path
import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.utils.name_normalizer import NameMapper, normalize_card_name
    HAS_NORMALIZER = True
except ImportError:
    HAS_NORMALIZER = False


def check_coverage(
    test_set_path: Path,
    embedding_path: Path,
    pairs_csv: Path | None = None,
    name_mapping_path: Path | None = None,
) -> dict[str, Any]:
    """Check vocabulary coverage."""
    # Load test set
    with open(test_set_path) as f:
        data = json.load(f)
    queries = data.get("queries", data) if isinstance(data, dict) else data
    test_queries = list(queries.keys())
    
    # Load embedding
    embedding = KeyedVectors.load(str(embedding_path))
    vocab = set(embedding.key_to_index.keys())
    
    # Load name mapping if available
    name_mapper = None
    if name_mapping_path and name_mapping_path.exists():
        if HAS_NORMALIZER:
            name_mapper = NameMapper.load_from_file(name_mapping_path)
    
    # Check coverage
    found_direct = []
    found_mapped = []
    not_found = []
    
    for query in test_queries:
        # Direct match
        if query in vocab:
            found_direct.append(query)
            continue
        
        # Mapped match
        if name_mapper:
            mapped = name_mapper.map_name(query)
            if mapped != query and mapped in vocab:
                found_mapped.append((query, mapped))
                continue
        
        # Normalized match
        query_norm = normalize_card_name(query) if HAS_NORMALIZER else query
        for vocab_name in vocab:
            vocab_norm = normalize_card_name(vocab_name) if HAS_NORMALIZER else vocab_name
            if query_norm == vocab_norm:
                found_mapped.append((query, vocab_name))
                break
        else:
            not_found.append(query)
    
    # Load training vocabulary for suggestions
    training_vocab = set()
    if pairs_csv and pairs_csv.exists() and HAS_DEPS:
        df = pd.read_csv(pairs_csv, nrows=10000)  # Sample
        training_vocab = set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
    
    # Find suggestions for not found
    suggestions = {}
    if HAS_NORMALIZER and training_vocab:
        for query in not_found[:10]:  # Limit to first 10
            query_norm = normalize_card_name(query)
            candidates = []
            for train_name in list(training_vocab)[:1000]:  # Sample
                train_norm = normalize_card_name(train_name)
                if query_norm in train_norm or train_norm in query_norm:
                    candidates.append(train_name)
                    if len(candidates) >= 5:
                        break
            if candidates:
                suggestions[query] = candidates
    
    return {
        "total_queries": len(test_queries),
        "found_direct": len(found_direct),
        "found_mapped": len(found_mapped),
        "not_found": len(not_found),
        "coverage": (len(found_direct) + len(found_mapped)) / len(test_queries) if test_queries else 0.0,
        "not_found_queries": not_found,
        "suggestions": suggestions,
    }


def main() -> int:
    """Check vocabulary coverage."""
    parser = argparse.ArgumentParser(description="Check vocabulary coverage")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--embedding", type=str, required=True, help="Embedding file (.wv)")
    parser.add_argument("--pairs-csv", type=str, help="Training pairs CSV (for suggestions)")
    parser.add_argument("--name-mapping", type=str, help="Name mapping JSON")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    test_set_path = Path(args.test_set)
    embedding_path = Path(args.embedding)
    pairs_csv = Path(args.pairs_csv) if args.pairs_csv else None
    name_mapping_path = Path(args.name_mapping) if args.name_mapping else None
    
    if not test_set_path.exists():
        print(f"❌ Test set not found: {test_set_path}")
        return 1
    
    if not embedding_path.exists():
        print(f"❌ Embedding not found: {embedding_path}")
        return 1
    
    print("Checking vocabulary coverage...")
    results = check_coverage(
        test_set_path=test_set_path,
        embedding_path=embedding_path,
        pairs_csv=pairs_csv,
        name_mapping_path=name_mapping_path,
    )
    
    print(f"\n📊 Coverage Results:")
    print(f"   Total queries: {results['total_queries']}")
    print(f"   Found direct: {results['found_direct']}")
    print(f"   Found mapped: {results['found_mapped']}")
    print(f"   Not found: {results['not_found']}")
    print(f"   Coverage: {results['coverage']:.1%}")
    
    if results['not_found_queries']:
        print(f"\n⚠️  Queries not in vocabulary ({len(results['not_found_queries'])}):")
        for q in results['not_found_queries'][:10]:
            print(f"     {q}")
            if q in results['suggestions']:
                print(f"       Suggestions: {', '.join(results['suggestions'][q][:3])}")
        if len(results['not_found_queries']) > 10:
            print(f"     ... and {len(results['not_found_queries']) - 10} more")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

