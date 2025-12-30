#!/usr/bin/env python3
"""
Diagnostic and Fix Script

Checks what's available, identifies issues, and provides fix guidance.
Works without heavy dependencies.
"""

import json
import sys
from pathlib import Path

def check_file(path: Path) -> tuple[bool, str]:
    """Check if file exists and return status."""
    if path.exists():
        size = path.stat().st_size
        return True, f"{size:,} bytes"
    return False, "missing"


def main() -> int:
    """Main diagnostic."""
    print("=" * 70)
    print("DeckSage Diagnostic and Fix Guide")
    print("=" * 70)
    print()
    
    # Check critical files
    print("Checking critical files...")
    print()
    
    issues = []
    available = []
    
    # Test set
    test_set_path = Path("experiments/test_set_canonical_magic.json")
    exists, info = check_file(test_set_path)
    if exists:
        print(f"  ✅ Test set: {test_set_path} ({info})")
        available.append("test_set")
        # Count queries
        try:
            with open(test_set_path) as f:
                data = json.load(f)
                queries = data.get("queries", data)
                print(f"    Queries: {len(queries)}")
        except Exception:
            pass
    else:
        print(f"  ❌ Test set: {test_set_path} (missing)")
        issues.append("test_set_missing")
    
    print()
    
    # Pairs CSV
    pairs_paths = [
        Path("data/processed/pairs_large.csv"),
        Path("src/backend/pairs_large.csv"),
        Path("backend/pairs_large.csv"),
    ]
    pairs_found = None
    for path in pairs_paths:
        exists, info = check_file(path)
        if exists:
            print(f"  ✅ Pairs CSV: {path} ({info})")
            pairs_found = path
            available.append("pairs_csv")
            break
    if not pairs_found:
        print(f"  ❌ Pairs CSV: Not found (tried: {[str(p) for p in pairs_paths]})")
        issues.append("pairs_csv_missing")
    
    print()
    
    # Embeddings
    embed_paths = [
        Path("data/embeddings/magic_128d_pecanpy.wv"),
        Path("data/embeddings/magic_64d_pecanpy.wv"),
        Path("src/backend/magic_128d_pecanpy.wv"),
    ]
    embed_found = None
    for path in embed_paths:
        exists, info = check_file(path)
        if exists:
            print(f"  ✅ Embeddings: {path} ({info})")
            embed_found = path
            available.append("embeddings")
            break
    if not embed_found:
        print(f"  ❌ Embeddings: Not found")
        issues.append("embeddings_missing")
    
    print()
    
    # Decks metadata
    decks_path = Path("data/processed/decks_with_metadata.jsonl")
    exists, info = check_file(decks_path)
    if exists:
        print(f"  ✅ Decks metadata: {decks_path} ({info})")
        available.append("decks_metadata")
    else:
        print(f"  ❌ Decks metadata: {decks_path} (missing)")
        issues.append("decks_metadata_missing")
    
    print()
    
    # Signals directory
    signals_dir = Path("experiments/signals")
    if signals_dir.exists():
        signal_files = list(signals_dir.glob("*.json"))
        if signal_files:
            print(f"  ✅ Signals directory: {signals_dir} ({len(signal_files)} files)")
            available.append("signals")
            for f in signal_files[:5]:
                print(f"    - {f.name}")
        else:
            print(f"  ⚠️ Signals directory: {signals_dir} (empty)")
            issues.append("signals_empty")
    else:
        print(f"  ❌ Signals directory: {signals_dir} (missing)")
        issues.append("signals_missing")
    
    print()
    print("=" * 70)
    print("Status Summary")
    print("=" * 70)
    print()
    
    print(f"Available: {len(available)}/{5}")
    print(f"Issues: {len(issues)}")
    print()
    
    # Recommendations
    print("=" * 70)
    print("Fix Recommendations")
    print("=" * 70)
    print()
    
    if "embeddings_missing" in issues:
        print("🔴 CRITICAL: Train embeddings")
        if pairs_found:
            print(f"   Command:")
            print(f"   uv run python -m src.ml.similarity.card_similarity_pecan \\")
            print(f"     --input {pairs_found} \\")
            print(f"     --output magic_128d --dim 128")
        else:
            print(f"   ⚠️ Need pairs CSV first")
        print()
    
    if "signals_missing" in issues or "signals_empty" in issues:
        print("🔴 CRITICAL: Compute signals")
        if pairs_found and decks_path.exists():
            print(f"   Command:")
            print(f"   uv run python -m src.ml.scripts.compute_and_cache_signals")
        else:
            print(f"   ⚠️ Need pairs CSV and decks metadata first")
        print()
    
    if "pairs_csv_missing" in issues:
        print("🔴 CRITICAL: Export graph from backend")
        print(f"   Command:")
        print(f"   cd src/backend")
        print(f"   go run ./cmd/export-decks-only <data_dir> pairs_large.csv")
        print()
    
    if "decks_metadata_missing" in issues:
        print("🟡 IMPORTANT: Export decks with metadata")
        print(f"   Need: data/processed/decks_with_metadata.jsonl")
        print()
    
    # What can be measured now
    if "test_set" in available:
        print("=" * 70)
        print("What Can Be Measured Now")
        print("=" * 70)
        print()
        
        if "pairs_csv" in available:
            print("  ✅ Can measure Jaccard similarity")
        else:
            print("  ❌ Cannot measure Jaccard (no pairs CSV)")
        
        if "embeddings" in available:
            print("  ✅ Can measure Embedding similarity")
        else:
            print("  ❌ Cannot measure Embedding (no embeddings)")
        
        if "test_set" in available:
            print("  ✅ Can measure Functional similarity (if tagger available)")
        print()
    
    # Next steps
    print("=" * 70)
    print("Next Steps (Prioritized)")
    print("=" * 70)
    print()
    
    steps = []
    
    if "pairs_csv_missing" in issues:
        steps.append("1. Export graph from backend (pairs CSV)")
    
    if "embeddings_missing" in issues and "pairs_csv" in available:
        steps.append("2. Train embeddings (requires pairs CSV)")
    
    if ("signals_missing" in issues or "signals_empty" in issues) and "pairs_csv" in available and "decks_metadata" in available:
        steps.append("3. Compute all signals")
    
    if "test_set" in available and ("pairs_csv" in available or "embeddings" in available):
        steps.append("4. Measure individual signal performance")
        print("   Run: uv run python -m src.ml.scripts.fix_and_measure_all")
    
    if not steps:
        steps.append("All critical data available - ready to measure and optimize!")
    
    for step in steps:
        print(f"  {step}")
    
    print()
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

