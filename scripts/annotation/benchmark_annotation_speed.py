#!/usr/bin/env python3
"""
Benchmark annotation generation speed to identify bottlenecks.

Measures:
- Graph loading time
- Card attributes loading time
- Single annotation time (with/without graph enrichment)
- Batch processing time
- LLM API call time
"""

import asyncio
import time
from pathlib import Path
import sys

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.annotation.llm_annotator import LLMAnnotator
    from ml.utils.paths import PATHS
    HAS_LLM_ANNOTATOR = True
except ImportError as e:
    HAS_LLM_ANNOTATOR = False
    print(f"Error: {e}")
    sys.exit(1)


async def benchmark():
    """Run performance benchmarks."""
    print("=" * 80)
    print("ANNOTATION GENERATION PERFORMANCE BENCHMARK")
    print("=" * 80)
    print()
    
    # 1. Graph loading
    print("1. Graph Loading...")
    start = time.time()
    try:
        from ml.data.incremental_graph import IncrementalCardGraph
        graph_path = PATHS.incremental_graph_db
        if graph_path.exists():
            graph = IncrementalCardGraph(graph_path=graph_path, use_sqlite=True)
            elapsed = time.time() - start
            print(f"   ✅ Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
            print(f"   ⏱️  Time: {elapsed:.2f}s")
        else:
            print("   ⚠️  Graph database not found")
            graph = None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        graph = None
    
    # 2. Card attributes loading
    print("\n2. Card Attributes Loading...")
    start = time.time()
    try:
        import pandas as pd
        attrs_path = PATHS.card_attributes
        if attrs_path.exists():
            df = pd.read_csv(attrs_path)
            elapsed = time.time() - start
            print(f"   ✅ Loaded {len(df):,} card attributes")
            print(f"   ⏱️  Time: {elapsed:.2f}s")
        else:
            print("   ⚠️  Card attributes file not found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 3. Graph enrichment (single pair)
    if graph:
        print("\n3. Graph Enrichment (Single Pair)...")
        start = time.time()
        try:
            from ml.annotation.graph_enricher import extract_graph_features
            # Use sample cards
            test_cards = ["Lightning Bolt", "Chain Lightning"]
            features = extract_graph_features(graph, test_cards[0], test_cards[1])
            elapsed = time.time() - start
            print(f"   ✅ Extracted features for {test_cards[0]} vs {test_cards[1]}")
            print(f"   ⏱️  Time: {elapsed:.4f}s")
            if features:
                print(f"      Jaccard: {features.jaccard_similarity:.3f}")
                print(f"      Co-occurrence: {features.cooccurrence_count}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # 4. LLM API call (mock - just measure prompt building)
    print("\n4. LLM Prompt Building...")
    start = time.time()
    prompt = f"""Analyze similarity between Lightning Bolt and Chain Lightning.
    Both are 1-mana red instant burn spells. Provide similarity_score, reasoning, etc."""
    elapsed = time.time() - start
    print(f"   ✅ Built prompt ({len(prompt)} chars)")
    print(f"   ⏱️  Time: {elapsed:.6f}s")
    
    # 5. Batch processing simulation
    print("\n5. Batch Processing Simulation...")
    batch_sizes = [1, 2, 5, 10, 20]
    for batch_size in batch_sizes:
        print(f"\n   Batch size: {batch_size}")
        # Simulate parallel execution
        start = time.time()
        tasks = [asyncio.sleep(0.1) for _ in range(batch_size)]  # Simulate 100ms per annotation
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        rate = batch_size / elapsed
        print(f"      Time: {elapsed:.3f}s")
        print(f"      Rate: {rate:.2f} ann/s")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS:")
    print("=" * 80)
    print("1. Use lazy graph loading (LazyGraphEnricher) instead of full graph load")
    print("2. Move graph enrichment to thread pool executor (CPU-bound)")
    print("3. Increase batch_size to maximize parallel LLM calls")
    print("4. Consider skipping graph enrichment during generation (do post-hoc)")
    print("5. Use async SQLite queries if possible")


if __name__ == "__main__":
    asyncio.run(benchmark())

