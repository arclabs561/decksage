#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Audit vocabulary coverage between embeddings and test sets.

Identifies:
- Which test queries are missing from embeddings
- Which embeddings have good coverage
- Name normalization issues
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add src to path for imports
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from gensim.models import KeyedVectors
    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    print("Error: gensim required")
    sys.exit(1)


def load_test_set(test_set_path: Path) -> dict[str, dict[str, Any]]:
    """Load test set."""
    with open(test_set_path) as f:
        data = json.load(f)
    
    if "queries" in data:
        return data["queries"]
    return data


def load_embedding(embedding_path: Path) -> KeyedVectors:
    """Load embedding."""
    return KeyedVectors.load(str(embedding_path))


def audit_coverage(
    test_set_path: Path,
    embedding_path: Path,
    name_mapping_path: Path | None = None,
) -> dict[str, Any]:
    """Audit vocabulary coverage."""
    test_set = load_test_set(test_set_path)
    embedding = load_embedding(embedding_path)
    
    # Load name mapping if available
    name_mapping = {}
    if name_mapping_path and name_mapping_path.exists():
        with open(name_mapping_path) as f:
            name_mapping = json.load(f)
    
    queries = list(test_set.keys())
    found = []
    missing = []
    mapped_found = []
    
    for query in queries:
        # Direct lookup
        if query in embedding:
            found.append(query)
        # Try name mapping
        elif query in name_mapping:
            mapped = name_mapping[query]
            if mapped in embedding:
                mapped_found.append((query, mapped))
            else:
                missing.append(query)
        else:
            missing.append(query)
    
    # Try case-insensitive and variations
    embedding_keys_lower = {k.lower(): k for k in embedding.key_to_index.keys()}
    case_variants = {}
    for query in missing[:]:
        query_lower = query.lower()
        if query_lower in embedding_keys_lower:
            actual_key = embedding_keys_lower[query_lower]
            case_variants[query] = actual_key
            missing.remove(query)
            found.append(query)
    
    coverage = len(found) / len(queries) if queries else 0.0
    
    return {
        "embedding": str(embedding_path),
        "test_set": str(test_set_path),
        "total_queries": len(queries),
        "found_direct": len(found),
        "found_mapped": len(mapped_found),
        "found_case_variant": len(case_variants),
        "missing": len(missing),
        "coverage": coverage,
        "missing_queries": missing,
        "mapped_queries": [{"original": q, "mapped": m} for q, m in mapped_found],
        "case_variants": case_variants,
    }


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audit vocabulary coverage")
    parser.add_argument("--test-set", type=Path, required=True, help="Test set JSON")
    parser.add_argument("--embedding", type=Path, required=True, help="Embedding .wv file")
    parser.add_argument("--name-mapping", type=Path, help="Name mapping JSON")
    parser.add_argument("--output", type=Path, help="Output JSON report")
    
    args = parser.parse_args()
    
    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1
    
    if not args.embedding.exists():
        print(f"Error: Embedding not found: {args.embedding}")
        return 1
    
    print(f"Auditing vocabulary coverage...")
    print(f"  Test set: {args.test_set}")
    print(f"  Embedding: {args.embedding}")
    
    result = audit_coverage(args.test_set, args.embedding, args.name_mapping)
    
    print(f"\nResults:")
    print(f"  Total queries: {result['total_queries']}")
    print(f"  Found (direct): {result['found_direct']}")
    print(f"  Found (mapped): {result['found_mapped']}")
    print(f"  Found (case variant): {result['found_case_variant']}")
    print(f"  Missing: {result['missing']}")
    print(f"  Coverage: {result['coverage']:.1%}")
    
    if result['missing_queries']:
        print(f"\nMissing queries ({len(result['missing_queries'])}):")
        for q in result['missing_queries'][:10]:
            print(f"    - {q}")
        if len(result['missing_queries']) > 10:
            print(f"    ... and {len(result['missing_queries']) - 10} more")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if result['coverage'] >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())

