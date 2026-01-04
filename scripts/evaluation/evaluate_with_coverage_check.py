#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Evaluation wrapper that ensures good vocabulary coverage.

Only evaluates embeddings with ≥80% vocabulary coverage to ensure
reliable results.
"""

import json
import sys
from pathlib import Path
from typing import Any

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
    
    parser = argparse.ArgumentParser(
        description="Evaluate with coverage check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate single embedding
  %(prog)s --embedding data/embeddings/multitask_final.wv
  
  # Evaluate with custom coverage threshold
  %(prog)s --embedding data/embeddings/multitask_final.wv --min-coverage 0.9
  
  # Evaluate all embeddings (auto-filter by coverage)
  %(prog)s --embeddings-dir data/embeddings --auto-filter
        """,
    )
    parser.add_argument(
        "--embedding",
        type=Path,
        help="Single embedding to evaluate",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Directory with embeddings (if evaluating multiple)",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic_improved.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        help="Minimum vocabulary coverage required (default: 0.8)",
    )
    parser.add_argument(
        "--auto-filter",
        action="store_true",
        help="Automatically filter embeddings by coverage",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file",
    )
    
    args = parser.parse_args()
    
    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1
    
    # Import evaluation script
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "ml" / "scripts"))
        from evaluate_all_embeddings import main as eval_main, load_test_set, evaluate_embedding
    except ImportError as e:
        print(f"Error: Could not import evaluation script: {e}")
        return 1
    
    # Load test set
    test_set = load_test_set(args.test_set)
    print(f"Loaded test set: {len(test_set)} queries")
    print(f"Minimum coverage required: {args.min_coverage:.0%}")
    print()
    
    # Get embeddings to evaluate
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
    
    # Check coverage for each
    results = {}
    passed = []
    failed = []
    
    for emb_path in sorted(embeddings_to_check):
        print(f"Checking {emb_path.name}...", end=" ", flush=True)
        try:
            coverage = check_coverage(args.test_set, emb_path)
            
            if coverage >= args.min_coverage:
                print(f"✓ {coverage:.1%} coverage - PASS")
                passed.append((emb_path, coverage))
            else:
                print(f"✗ {coverage:.1%} coverage - FAIL (need {args.min_coverage:.0%})")
                failed.append((emb_path, coverage))
                if not args.auto_filter:
                    continue
            
            # Evaluate if passed
            if args.auto_filter or coverage >= args.min_coverage:
                print(f"  Evaluating...", end=" ", flush=True)
                embedding = KeyedVectors.load(str(emb_path))
                eval_result = evaluate_embedding(
                    embedding,
                    test_set,
                    top_k=10,
                    verbose=False,
                )
                print(f"✓ P@10={eval_result['p@10']:.4f}, MRR={eval_result['mrr']:.4f}")
                results[emb_path.name] = {
                    "path": str(emb_path),
                    "coverage": coverage,
                    **eval_result,
                }
        except Exception as e:
            print(f"✗ Error: {e}")
            failed.append((emb_path, None))
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Passed (≥{args.min_coverage:.0%} coverage): {len(passed)}")
    print(f"Failed (<{args.min_coverage:.0%} coverage): {len(failed)}")
    print(f"Evaluated: {len(results)}")
    
    if results:
        print()
        print("Results:")
        for name, result in sorted(results.items(), key=lambda x: x[1].get('p@10', 0), reverse=True):
            print(f"  {name}:")
            print(f"    Coverage: {result['coverage']:.1%}")
            print(f"    P@10: {result['p@10']:.4f}")
            print(f"    MRR: {result['mrr']:.4f}")
            print(f"    Queries: {result.get('num_evaluated', result.get('num_queries', 0))}")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({
                "test_set": str(args.test_set),
                "min_coverage": args.min_coverage,
                "summary": {
                    "total": len(embeddings_to_check),
                    "passed": len(passed),
                    "failed": len(failed),
                    "evaluated": len(results),
                },
                "results": results,
                "failed": [{"path": str(p), "coverage": c} for p, c in failed],
            }, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())

