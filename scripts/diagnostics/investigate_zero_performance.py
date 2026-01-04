#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Investigate why embeddings have P@10 = 0.0.

Checks:
- Vocabulary size
- Test query coverage
- Similarity function works
- Test set format
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


def investigate_embedding(
    embedding_path: Path,
    test_set_path: Path,
) -> dict[str, Any]:
    """Investigate why embedding might have P@10 = 0.0."""
    embedding = KeyedVectors.load(str(embedding_path))
    
    with open(test_set_path) as f:
        test_data = json.load(f)
    
    test_set = test_data.get("queries", test_data)
    
    issues = []
    diagnostics = {
        "embedding": str(embedding_path),
        "vocab_size": len(embedding),
        "test_queries": len(test_set),
        "issues": issues,
    }
    
    # Check 1: Vocabulary size
    if len(embedding) < 100:
        issues.append({
            "severity": "high",
            "issue": "Very small vocabulary",
            "detail": f"Only {len(embedding)} cards in embedding",
        })
    
    # Check 2: Test query coverage
    queries_in_vocab = []
    queries_not_in_vocab = []
    
    for query in test_set.keys():
        if query in embedding:
            queries_in_vocab.append(query)
        else:
            queries_not_in_vocab.append(query)
    
    coverage = len(queries_in_vocab) / len(test_set) if test_set else 0.0
    diagnostics["coverage"] = coverage
    diagnostics["queries_in_vocab"] = len(queries_in_vocab)
    diagnostics["queries_not_in_vocab"] = len(queries_not_in_vocab)
    
    if coverage < 0.5:
        issues.append({
            "severity": "high",
            "issue": "Poor vocabulary coverage",
            "detail": f"Only {coverage:.1%} of test queries in vocabulary ({len(queries_in_vocab)}/{len(test_set)})",
        })
    
    # Check 3: Similarity function works
    if queries_in_vocab:
        test_query = queries_in_vocab[0]
        try:
            similar = embedding.most_similar(test_query, topn=10)
            diagnostics["similarity_works"] = True
            diagnostics["sample_similar"] = similar[:3]  # First 3
        except Exception as e:
            issues.append({
                "severity": "critical",
                "issue": "Similarity function fails",
                "detail": f"Error: {e}",
            })
            diagnostics["similarity_works"] = False
    else:
        issues.append({
            "severity": "critical",
            "issue": "No test queries in vocabulary",
            "detail": "Cannot test similarity function",
        })
        diagnostics["similarity_works"] = None
    
    # Check 4: Test set format
    sample_query = list(test_set.keys())[0] if test_set else None
    if sample_query:
        labels = test_set[sample_query]
        if not isinstance(labels, dict):
            issues.append({
                "severity": "medium",
                "issue": "Test set format issue",
                "detail": f"Labels for '{sample_query}' are not a dict: {type(labels)}",
            })
        else:
            relevant_levels = ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]
            has_relevant = any(labels.get(level, []) for level in relevant_levels)
            if not has_relevant:
                issues.append({
                    "severity": "high",
                    "issue": "No relevant labels",
                    "detail": f"Query '{sample_query}' has no relevant labels",
                })
    
    diagnostics["issues"] = issues
    diagnostics["num_issues"] = len(issues)
    diagnostics["critical_issues"] = len([i for i in issues if i["severity"] == "critical"])
    diagnostics["high_issues"] = len([i for i in issues if i["severity"] == "high"])
    
    return diagnostics


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Investigate zero performance")
    parser.add_argument(
        "--embedding",
        type=Path,
        required=True,
        help="Embedding .wv file",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )
    
    args = parser.parse_args()
    
    if not args.embedding.exists():
        print(f"Error: Embedding not found: {args.embedding}")
        return 1
    
    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1
    
    print(f"Investigating {args.embedding.name}...")
    print(f"  Test set: {args.test_set}")
    print()
    
    result = investigate_embedding(args.embedding, args.test_set)
    
    print("Diagnostics:")
    print(f"  Vocabulary size: {result['vocab_size']:,}")
    print(f"  Test queries: {result['test_queries']}")
    print(f"  Coverage: {result['coverage']:.1%} ({result['queries_in_vocab']}/{result['test_queries']})")
    print(f"  Similarity works: {result['similarity_works']}")
    print()
    
    if result['issues']:
        print("Issues found:")
        for issue in result['issues']:
            severity_icon = "🔴" if issue['severity'] == 'critical' else "🟠" if issue['severity'] == 'high' else "🟡"
            print(f"  {severity_icon} [{issue['severity'].upper()}] {issue['issue']}")
            print(f"      {issue['detail']}")
    else:
        print("✓ No issues found - embedding should work")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if result['critical_issues'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

