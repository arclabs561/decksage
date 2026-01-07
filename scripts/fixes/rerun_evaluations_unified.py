#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Re-run evaluations using unified test set with proper vocabulary filtering.

Ensures:
- Uses unified test set (940 queries, 94.98% quality)
- Only evaluates embeddings with ≥80% vocabulary coverage
- Evaluates on all queries (not just subset)
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


def check_coverage(test_set_path: Path, embedding_path: Path) -> float:
    """Check vocabulary coverage."""
    with open(test_set_path) as f:
        data = json.load(f)

    test_set = data.get("queries", data)
    embedding = KeyedVectors.load(str(embedding_path))

    queries = list(test_set.keys())
    in_vocab = sum(1 for q in queries if q in embedding)

    return in_vocab / len(queries) if queries else 0.0


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Re-run evaluations with unified test set")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_unified_magic.json"),
        help="Unified test set JSON",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Embeddings directory",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        help="Minimum vocabulary coverage (default: 0.8)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/evaluation_results_unified.json"),
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

    print(f"Using unified test set: {len(test_set)} queries")
    print(f"Minimum coverage required: {args.min_coverage:.0%}")
    print()

    # Find embeddings
    if not args.embeddings_dir.exists():
        print(f"Error: Embeddings directory not found: {args.embeddings_dir}")
        return 1

    embedding_files = list(args.embeddings_dir.glob("*.wv"))
    embedding_files.extend(list(args.embeddings_dir.glob("**/*.wv")))

    if not embedding_files:
        print("Error: No embeddings found")
        return 1

    print(f"Checking {len(embedding_files)} embeddings...")
    print()

    # Check coverage and filter
    embeddings_to_evaluate = []
    for emb_path in sorted(embedding_files):
        try:
            coverage = check_coverage(args.test_set, emb_path)
            if coverage >= args.min_coverage:
                embeddings_to_evaluate.append((emb_path, coverage))
                print(f"✓ {emb_path.name}: {coverage:.1%} coverage")
            else:
                print(f"✗ {emb_path.name}: {coverage:.1%} coverage (below {args.min_coverage:.0%})")
        except Exception as e:
            print(f"✗ {emb_path.name}: Error - {e}")

    print()
    print(f"Found {len(embeddings_to_evaluate)} embeddings with ≥{args.min_coverage:.0%} coverage")
    print()

    if not embeddings_to_evaluate:
        print("No embeddings meet coverage requirement")
        return 1

    # Import evaluation function
    try:
        sys.path.insert(0, str(src_dir / "ml" / "scripts"))
        from evaluate_all_embeddings import evaluate_embedding
    except ImportError:
        print("Error: Could not import evaluation function")
        return 1

    # Evaluate each embedding
    print("Evaluating embeddings...")
    print()

    results = {}
    for emb_path, coverage in embeddings_to_evaluate:
        print(f"Evaluating {emb_path.name}...", end=" ", flush=True)
        try:
            embedding = KeyedVectors.load(str(emb_path))
            result = evaluate_embedding(
                embedding,
                test_set,
                top_k=10,
                verbose=False,
            )

            result["coverage"] = coverage
            results[emb_path.name] = result

            num_eval = result.get("num_evaluated", 0)
            p_at_10 = result.get("p@10", 0)
            print(f"✓ P@10={p_at_10:.4f}, {num_eval}/{len(test_set)} queries")
        except Exception as e:
            print(f"✗ Error: {e}")

    print()
    print("=" * 70)
    print("Results Summary")
    print("=" * 70)
    print()

    if not results:
        print("No results generated")
        return 1

    # Sort by P@10
    sorted_results = sorted(results.items(), key=lambda x: x[1].get("p@10", 0), reverse=True)

    print("Top results:")
    for name, result in sorted_results[:10]:
        coverage = result.get("coverage", 0)
        p_at_10 = result.get("p@10", 0)
        num_eval = result.get("num_evaluated", 0)
        print(f"  {name}:")
        print(f"    P@10: {p_at_10:.4f}")
        print(f"    Coverage: {coverage:.1%}")
        print(f"    Queries: {num_eval}/{len(test_set)}")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(
            {
                "test_set": str(args.test_set),
                "test_set_queries": len(test_set),
                "min_coverage": args.min_coverage,
                "summary": {
                    "total_embeddings_checked": len(embedding_files),
                    "embeddings_evaluated": len(results),
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
