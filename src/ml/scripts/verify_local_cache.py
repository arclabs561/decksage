#!/usr/bin/env python3
"""
Verify local cache data is properly saved and accessible.

Checks:
- LLM cache directory and stats
- Embedding files existence
- Graph data existence
- Cache directory structure
"""

# /// script
# requires-python = ">=3.10"
# ///

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ml.utils.llm_cache import LLMCache, load_config
from ml.utils.paths import PATHS


def check_llm_cache() -> dict:
    """Check LLM cache status."""
    try:
        config = load_config()
        cache = LLMCache(config=config)
        stats = cache.stats()
        cache_dir = Path(stats["dir"])

        return {
            "exists": cache_dir.exists(),
            "path": str(cache_dir),
            "bypass": stats["bypass"],
            "ttl_seconds": stats["ttl_seconds"],
            "size_limit_mb": stats["size_limit_mb"],
            "backend": stats["backend"],
            "size_bytes": sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) if cache_dir.exists() else 0,
        }
    except Exception as e:
        return {"error": str(e)}


def check_embeddings() -> dict:
    """Check embedding files."""
    emb_dir = PATHS.embeddings
    if not emb_dir.exists():
        return {"exists": False, "path": str(emb_dir)}
    
    files = list(emb_dir.glob("*.wv"))
    return {
        "exists": True,
        "path": str(emb_dir),
        "count": len(files),
        "files": [f.name for f in files],
 "total_size_bytes": sum(f.stat().st_size for f in files),
 }


def check_graphs() -> dict:
    """Check graph data files."""
    graph_dir = PATHS.graphs
    if not graph_dir.exists():
        return {"exists": False, "path": str(graph_dir)}
    
    files = list(graph_dir.glob("*.edg"))
    return {
        "exists": True,
 "path": str(graph_dir),
 "count": len(files),
 "files": [f.name for f in files],
 "total_size_bytes": sum(f.stat().st_size for f in files),
 }


def check_processed_data() -> dict:
 """Check processed data files."""
 pairs = PATHS.pairs_large
 metadata = PATHS.decks_with_metadata
 
 return {
 "pairs_large": {
 "exists": pairs.exists(),
 "path": str(pairs),
 "size_bytes": pairs.stat().st_size if pairs.exists() else 0,
 },
 "decks_with_metadata": {
 "exists": metadata.exists(),
 "path": str(metadata),
 "size_bytes": metadata.stat().st_size if metadata.exists() else 0,
 },
 }


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main() -> None:
    """Verify all local cache data."""
    print("=" * 70)
    print("Local Cache Verification")
    print("=" * 70)
    print()
    
    # LLM Cache
    print("## LLM Cache")
    llm_cache = check_llm_cache()
    if "error" in llm_cache:
        print(f" Error: Error: {llm_cache['error']}")
    else:
        print(f" Path: {llm_cache['path']}")
        print(f" Exists: {'✓' if llm_cache['exists'] else '✗'}")
        print(f" Size: {format_size(llm_cache.get('size_bytes', 0))}")
        print(f" Bypass: {llm_cache['bypass']}")
        print(f" TTL: {llm_cache['ttl_seconds']} seconds")
        print(f" Size Limit: {llm_cache['size_limit_mb']} MB")
        print(f" Backend: {llm_cache['backend']}")
    print()
    
    # Embeddings
    print("## Embeddings")
    embeddings = check_embeddings()
    print(f" Path: {embeddings['path']}")
    print(f" Exists: {'✓' if embeddings.get('exists') else '✗'}")
    if embeddings.get('exists'):
        print(f" Count: {embeddings['count']}")
        print(f" Total Size: {format_size(embeddings['total_size_bytes'])}")
        for f in embeddings.get('files', [])[:5]:
            print(f" - {f}")
        if embeddings['count'] > 5:
            print(f" ... and {embeddings['count'] - 5} more")
    print()
    
    # Graphs
    print("## Graph Data")
    graphs = check_graphs()
    print(f" Path: {graphs['path']}")
    print(f" Exists: {'✓' if graphs.get('exists') else '✗'}")
    if graphs.get('exists'):
        print(f" Count: {graphs['count']}")
        print(f" Total Size: {format_size(graphs['total_size_bytes'])}")
        for f in graphs.get('files', [])[:5]:
            print(f" - {f}")
        if graphs['count'] > 5:
            print(f" ... and {graphs['count'] - 5} more")
    print()
    
    # Processed Data
    print("## Processed Data")
    processed = check_processed_data()
    for name, info in processed.items():
        print(f" {name}:")
        print(f" Exists: {'✓' if info['exists'] else '✗'}")
        if info['exists']:
            print(f" Path: {info['path']}")
            print(f" Size: {format_size(info['size_bytes'])}")
    print()
    
    print("=" * 70)
    print("Verification Complete")
    print("=" * 70)


if __name__ == "__main__":
 main()

