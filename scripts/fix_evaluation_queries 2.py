#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Fix evaluation to use all queries, not just a subset.

Re-runs evaluation ensuring all 38 queries are used.
"""

import json
import sys
from pathlib import Path


# Add src to path
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


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix evaluation to use all queries")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--embedding",
        type=Path,
        help="Specific embedding to test (or test all)",
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
        default=Path("experiments/fixed_evaluation_results.json"),
        help="Output JSON",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    # Load test set
    with open(args.test_set) as f:
        test_data = json.load(f)

    test_set = test_data.get("queries", test_data)
    if not isinstance(test_set, dict):
        print("Error: Test set format invalid")
        return 1

    print(f"Loaded test set: {len(test_set)} queries")
    print(f"Sample queries: {', '.join(list(test_set.keys())[:5])}")
    print()

    # Get embeddings to test
    if args.embedding:
        embeddings_to_test = [args.embedding]
    else:
        embeddings_dir = args.embeddings_dir
        if not embeddings_dir.exists():
            print(f"Error: Embeddings directory not found: {embeddings_dir}")
            return 1

        embeddings_to_test = list(embeddings_dir.glob("*.wv"))
        embeddings_to_test.extend(list(embeddings_dir.glob("**/*.wv")))

    if not embeddings_to_test:
        print("Error: No embeddings found")
        return 1

    print(f"Testing {len(embeddings_to_test)} embeddings...")
    print()

    # Import evaluation function
    try:
        sys.path.insert(0, str(src_dir / "ml" / "scripts"))
        from evaluate_all_embeddings import evaluate_embedding
    except ImportError:
        print("Error: Could not import evaluation function")
        return 1

    results = {}
    for emb_path in sorted(embeddings_to_test):
        print(f"Evaluating {emb_path.name}...", end=" ", flush=True)
        try:
            embedding = KeyedVectors.load(str(emb_path))

            # Check coverage first
            queries_in_vocab = [q for q in test_set.keys() if q in embedding]
            coverage = len(queries_in_vocab) / len(test_set) if test_set else 0.0

            if coverage < 0.5:
                print(f"✗ {coverage:.1%} coverage - SKIP")
                continue

            # Evaluate
            result = evaluate_embedding(
                embedding,
                test_set,
                top_k=10,
                verbose=False,
            )

            print(
                f"✓ P@10={result['p@10']:.4f}, {result.get('num_evaluated', 0)}/{len(test_set)} queries"
            )

            results[emb_path.name] = {
                "path": str(emb_path),
                "coverage": coverage,
                **result,
            }
        except Exception as e:
            print(f"✗ Error: {e}")

    print()
    print("=" * 70)
    print("Results")
    print("=" * 70)

    if not results:
        print("No embeddings passed coverage check")
        return 1

    # Sort by P@10
    sorted_results = sorted(results.items(), key=lambda x: x[1].get("p@10", 0), reverse=True)

    print("\nTop results (≥50% coverage):")
    for name, result in sorted_results[:10]:
        coverage = result.get("coverage", 0)
        p_at_10 = result.get("p@10", 0)
        num_eval = result.get("num_evaluated", 0)
        print(f"  {name}:")
        print(f"    P@10: {p_at_10:.4f}")
        print(f"    Coverage: {coverage:.1%} ({num_eval}/{len(test_set)} queries)")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(
            {
                "test_set": str(args.test_set),
                "test_set_queries": len(test_set),
                "summary": {
                    "total_embeddings": len(embeddings_to_test),
                    "evaluated": len(results),
                    "best_p@10": max([r.get("p@10", 0) for r in results.values()])
                    if results
                    else 0.0,
                },
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\nResults saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
