#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Validate embedding quality.

Checks:
- Vocabulary size
- Vector dimensions
- Test set coverage
- Similarity function works
- Embedding format valid
"""

import json
import sys
from pathlib import Path
from typing import Any

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


def validate_embedding(embedding_path: Path, test_set_path: Path | None = None) -> dict[str, Any]:
    """Validate single embedding."""
    issues = []
    stats = {}
    
    try:
        embedding = KeyedVectors.load(str(embedding_path))
        
        stats["vocab_size"] = len(embedding)
        stats["vector_dim"] = embedding.vector_size if hasattr(embedding, 'vector_size') else None
        
        # Check vocabulary size
        if stats["vocab_size"] < 100:
            issues.append(f"Very small vocabulary: {stats['vocab_size']} cards")
        elif stats["vocab_size"] < 1000:
            issues.append(f"Small vocabulary: {stats['vocab_size']} cards")
        
        # Check vector dimension
        if stats["vector_dim"] is None:
            issues.append("Vector dimension not available")
        elif stats["vector_dim"] < 64:
            issues.append(f"Small vector dimension: {stats['vector_dim']}")
        
        # Test similarity function
        if stats["vocab_size"] > 0:
            sample_key = list(embedding.key_to_index.keys())[0]
            try:
                similar = embedding.most_similar(sample_key, topn=5)
                stats["similarity_works"] = True
                stats["sample_similar_count"] = len(similar)
            except Exception as e:
                issues.append(f"Similarity function failed: {e}")
                stats["similarity_works"] = False
        else:
            issues.append("Cannot test similarity: empty vocabulary")
            stats["similarity_works"] = False
        
        # Check test set coverage
        if test_set_path and test_set_path.exists():
            with open(test_set_path) as f:
                test_data = json.load(f)
            
            test_queries = test_data.get("queries", test_data)
            if isinstance(test_queries, dict):
                queries = list(test_queries.keys())
                in_vocab = sum(1 for q in queries if q in embedding)
                coverage = in_vocab / len(queries) if queries else 0.0
                
                stats["test_coverage"] = coverage
                stats["test_queries"] = len(queries)
                stats["test_queries_in_vocab"] = in_vocab
                
                if coverage < 0.5:
                    issues.append(f"Poor test coverage: {coverage:.1%} ({in_vocab}/{len(queries)})")
                elif coverage < 0.8:
                    issues.append(f"Moderate test coverage: {coverage:.1%} ({in_vocab}/{len(queries)})")
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "issues": [f"Failed to load: {e}"],
        }
    
    return {
        "valid": len(issues) == 0,
        "embedding": str(embedding_path),
        "stats": stats,
        "issues": issues,
        "quality_score": calculate_quality_score(stats, issues),
    }


def calculate_quality_score(stats: dict[str, Any], issues: list[str]) -> float:
    """Calculate quality score (0-1)."""
    score = 1.0
    
    # Penalize small vocabulary
    if stats.get("vocab_size", 0) < 1000:
        score -= 0.3
    elif stats.get("vocab_size", 0) < 5000:
        score -= 0.1
    
    # Penalize poor test coverage
    if "test_coverage" in stats:
        if stats["test_coverage"] < 0.5:
            score -= 0.4
        elif stats["test_coverage"] < 0.8:
            score -= 0.2
    
    # Penalize similarity issues
    if not stats.get("similarity_works", True):
        score -= 0.3
    
    # Penalize issues
    score -= len(issues) * 0.05
    
    return max(0.0, min(1.0, score))


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate embedding quality")
    parser.add_argument(
        "--embedding",
        type=Path,
        help="Single embedding to validate",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Directory with embeddings",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set for coverage check",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )
    
    args = parser.parse_args()
    
    if args.embedding:
        embeddings_to_check = [args.embedding]
    else:
        if not args.embeddings_dir.exists():
            print(f"Error: Embeddings directory not found: {args.embeddings_dir}")
            return 1
        
        embeddings_to_check = list(args.embeddings_dir.glob("*.wv"))
        embeddings_to_check.extend(list(args.embeddings_dir.glob("**/*.wv")))
    
    if not embeddings_to_check:
        print("Error: No embeddings found")
        return 1
    
    print(f"Validating {len(embeddings_to_check)} embeddings...")
    if args.test_set.exists():
        print(f"Test set: {args.test_set}")
    print()
    
    results = {}
    for emb_path in sorted(embeddings_to_check):
        print(f"Validating {emb_path.name}...", end=" ", flush=True)
        result = validate_embedding(emb_path, args.test_set if args.test_set.exists() else None)
        results[emb_path.name] = result
        
        if result["valid"]:
            print(f"✓ Quality: {result['quality_score']:.1%}")
        else:
            print(f"✗ {len(result.get('issues', []))} issues")
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    valid = [r for r in results.values() if r["valid"]]
    invalid = [r for r in results.values() if not r["valid"]]
    
    print(f"Valid: {len(valid)}/{len(results)}")
    print(f"Invalid: {len(invalid)}/{len(results)}")
    
    if valid:
        best = max(valid, key=lambda x: x.get("quality_score", 0))
        print(f"\nBest quality: {best['quality_score']:.1%}")
        print(f"  Embedding: {Path(best['embedding']).name}")
        print(f"  Vocab size: {best['stats'].get('vocab_size', 0):,}")
        if 'test_coverage' in best['stats']:
            print(f"  Test coverage: {best['stats']['test_coverage']:.1%}")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({
                "test_set": str(args.test_set) if args.test_set.exists() else None,
                "summary": {
                    "total": len(results),
                    "valid": len(valid),
                    "invalid": len(invalid),
                },
                "results": results,
            }, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if len(invalid) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

