#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Fix evaluation coverage issues.

Ensures all test queries are evaluated, not just a subset.
Reports vocabulary mismatches and suggests fixes.
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


def check_embedding_coverage(
    test_set: dict[str, dict[str, Any]],
    embedding_path: Path,
) -> dict[str, Any]:
    """Check which queries are in embedding."""
    embedding = KeyedVectors.load(str(embedding_path))

    queries = list(test_set.keys())
    in_vocab = []
    not_in_vocab = []

    for query in queries:
        if query in embedding:
            in_vocab.append(query)
        else:
            not_in_vocab.append(query)

    return {
        "embedding": str(embedding_path),
        "total_queries": len(queries),
        "in_vocab": len(in_vocab),
        "not_in_vocab": len(not_in_vocab),
        "coverage": len(in_vocab) / len(queries) if queries else 0.0,
        "missing_queries": not_in_vocab,
    }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix evaluation coverage")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--embedding",
        type=Path,
        help="Specific embedding to check (or check all)",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Embeddings directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/coverage_fix_report.json"),
        help="Output report",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    test_set = load_test_set(args.test_set)
    print(f"Loaded test set: {len(test_set)} queries")

    if args.embedding:
        embeddings_to_check = [args.embedding]
    else:
        embeddings_dir = args.embeddings_dir
        if not embeddings_dir.exists():
            print(f"Error: Embeddings directory not found: {embeddings_dir}")
            return 1

        embeddings_to_check = list(embeddings_dir.glob("*.wv"))
        embeddings_to_check.extend(list(embeddings_dir.glob("**/*.wv")))

    if not embeddings_to_check:
        print("Error: No embeddings found")
        return 1

    print(f"Checking {len(embeddings_to_check)} embeddings...")
    print()

    results = {}
    for emb_path in sorted(embeddings_to_check):
        print(f"Checking {emb_path.name}...", end=" ", flush=True)
        try:
            coverage = check_embedding_coverage(test_set, emb_path)
            results[emb_path.name] = coverage

            if coverage["coverage"] >= 0.8:
                print(
                    f"✓ {coverage['coverage']:.1%} ({coverage['in_vocab']}/{coverage['total_queries']})"
                )
            elif coverage["coverage"] >= 0.5:
                print(
                    f"⚠ {coverage['coverage']:.1%} ({coverage['in_vocab']}/{coverage['total_queries']})"
                )
            else:
                print(
                    f"✗ {coverage['coverage']:.1%} ({coverage['in_vocab']}/{coverage['total_queries']})"
                )
        except Exception as e:
            print(f"✗ Error: {e}")
            results[emb_path.name] = {"error": str(e)}

    # Find best embeddings
    working = [(name, r) for name, r in results.items() if "coverage" in r and r["coverage"] >= 0.8]
    working.sort(key=lambda x: x[1]["coverage"], reverse=True)

    print("\n" + "=" * 70)
    print("Recommendations")
    print("=" * 70)

    if working:
        print("\nBest embeddings (≥80% coverage):")
        for name, r in working[:5]:
            print(f"  - {name}: {r['coverage']:.1%} ({r['in_vocab']}/{r['total_queries']} queries)")
    else:
        print("\n⚠ No embeddings have ≥80% coverage!")
        print("  This means evaluations will skip most queries.")
        print("  Recommendation: Fix vocabulary mismatch or retrain embeddings.")

    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(
            {
                "test_set": str(args.test_set),
                "test_set_queries": len(test_set),
                "summary": {
                    "total_embeddings": len(embeddings_to_check),
                    "working": len(
                        [r for r in results.values() if "coverage" in r and r["coverage"] >= 0.8]
                    ),
                    "partial": len(
                        [
                            r
                            for r in results.values()
                            if "coverage" in r and 0.5 <= r["coverage"] < 0.8
                        ]
                    ),
                    "broken": len(
                        [r for r in results.values() if "coverage" in r and r["coverage"] < 0.5]
                    ),
                },
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\nReport saved to: {args.output}")

    return 0 if working else 1


if __name__ == "__main__":
    sys.exit(main())
