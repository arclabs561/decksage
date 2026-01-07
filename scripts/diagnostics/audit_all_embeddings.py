#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Audit all embeddings for vocabulary coverage.

Scans all .wv files and checks coverage against test sets.
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


def audit_embedding(test_set_path: Path, embedding_path: Path) -> dict[str, Any]:
    """Quick audit of single embedding."""
    import sys
    from pathlib import Path as PathType

    # Add scripts to path
    script_dir = PathType(__file__).parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    from audit_vocabulary_coverage import audit_coverage

    return audit_coverage(test_set_path, embedding_path)


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Audit all embeddings")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set JSON",
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
        default=Path("experiments/vocabulary_coverage_audit.json"),
        help="Output JSON report",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    embeddings_dir = args.embeddings_dir
    if not embeddings_dir.exists():
        print(f"Error: Embeddings directory not found: {embeddings_dir}")
        return 1

    # Find all .wv files
    embedding_files = list(embeddings_dir.glob("*.wv"))
    embedding_files.extend(list(embeddings_dir.glob("**/*.wv")))

    if not embedding_files:
        print(f"Error: No .wv files found in {embeddings_dir}")
        return 1

    print(f"Found {len(embedding_files)} embedding files")
    print(f"Auditing against test set: {args.test_set}")
    print()

    results = {}
    for emb_path in sorted(embedding_files):
        print(f"Auditing {emb_path.name}...", end=" ", flush=True)
        try:
            result = audit_embedding(args.test_set, emb_path)
            results[emb_path.name] = {
                "path": str(emb_path),
                "coverage": result["coverage"],
                "total_queries": result["total_queries"],
                "found": result["found_direct"],
                "missing": result["missing"],
                "missing_queries": result["missing_queries"][:5],  # Sample
            }
            print(f"✓ {result['coverage']:.1%} coverage ({result['found_direct']}/{result['total_queries']})")
        except Exception as e:
            print(f"✗ Error: {e}")
            results[emb_path.name] = {
                "path": str(emb_path),
                "error": str(e),
            }

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)

    working = [r for r in results.values() if "coverage" in r and r["coverage"] >= 0.8]
    partial = [r for r in results.values() if "coverage" in r and 0.5 <= r["coverage"] < 0.8]
    broken = [r for r in results.values() if "coverage" in r and r["coverage"] < 0.5]
    errors = [r for r in results.values() if "error" in r]

    print(f"Working (≥80% coverage): {len(working)}")
    for r in sorted(working, key=lambda x: x["coverage"], reverse=True)[:5]:
        print(f"  - {Path(r['path']).name}: {r['coverage']:.1%}")

    print(f"\nPartial (50-79% coverage): {len(partial)}")
    for r in sorted(partial, key=lambda x: x["coverage"], reverse=True)[:5]:
        print(f"  - {Path(r['path']).name}: {r['coverage']:.1%}")

    print(f"\nBroken (<50% coverage): {len(broken)}")
    for r in sorted(broken, key=lambda x: x.get("coverage", 0))[:5]:
        print(f"  - {Path(r['path']).name}: {r.get('coverage', 0):.1%}")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for r in errors[:5]:
            print(f"  - {Path(r['path']).name}: {r['error']}")

    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump({
            "test_set": str(args.test_set),
            "embeddings_dir": str(embeddings_dir),
            "summary": {
                "total": len(embedding_files),
                "working": len(working),
                "partial": len(partial),
                "broken": len(broken),
                "errors": len(errors),
            },
            "results": results,
        }, f, indent=2)

    print(f"\nFull report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
