#!/usr/bin/env python3
"""Profile annotation enrichment to identify bottlenecks."""

import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.annotation.lazy_graph_enricher import LazyGraphEnricher
from ml.annotation.graph_enricher import enrich_annotation_with_graph
from ml.utils.paths import PATHS


def load_card_attributes() -> dict[str, dict] | None:
    """Load card attributes from CSV."""
    import pandas as pd
    
    attrs_path = Path(__file__).parent.parent.parent / "data" / "processed" / "card_attributes_enriched.csv"
    if not attrs_path.exists():
        return None
    
    df = pd.read_csv(attrs_path)
    return df.set_index("name").to_dict("index")


def profile_enrichment():
    """Profile a single annotation enrichment."""
    graph_path = PATHS.incremental_graph_db
    ann_file = Path("annotations/magic_llm_annotations.jsonl")
    
    if not ann_file.exists():
        print(f"Error: {ann_file} not found")
        return
    
    # Load one annotation
    with open(ann_file) as f:
        line = f.readline().strip()
        annotation = json.loads(line)
    
    card_attributes = load_card_attributes()
    
    print(f"Profiling enrichment for: {annotation.get('card1')} ↔ {annotation.get('card2')}")
    print(f"Graph DB: {graph_path}")
    print(f"Graph DB exists: {graph_path.exists()}")
    print()
    
    # Profile with cProfile
    profiler = cProfile.Profile()
    profiler.enable()
    
    try:
        with LazyGraphEnricher(graph_path, game="MTG") as enricher:
            # Time individual operations
            card1 = annotation.get("card1")
            card2 = annotation.get("card2")
            
            print("Timing individual operations...")
            
            # Time get_neighbors
            start = time.time()
            neighbors1 = enricher.get_neighbors(card1)
            neighbors2 = enricher.get_neighbors(card2)
            neighbor_time = time.time() - start
            print(f"  get_neighbors: {neighbor_time*1000:.1f}ms (card1: {len(neighbors1)}, card2: {len(neighbors2)})")
            
            # Time get_edge
            start = time.time()
            edge = enricher.get_edge(card1, card2)
            edge_time = time.time() - start
            print(f"  get_edge: {edge_time*1000:.1f}ms")
            
            # Time extract_graph_features
            start = time.time()
            graph_features = enricher.extract_graph_features(card1, card2)
            features_time = time.time() - start
            print(f"  extract_graph_features: {features_time*1000:.1f}ms")
            
            # Time enrich_annotation_with_graph
            start = time.time()
            enriched = enrich_annotation_with_graph(annotation, None, card_attributes)
            enrich_time = time.time() - start
            print(f"  enrich_annotation_with_graph: {enrich_time*1000:.1f}ms")
            
            total_time = neighbor_time + edge_time + features_time + enrich_time
            print(f"\nTotal time: {total_time*1000:.1f}ms")
            print(f"  Graph operations: {(neighbor_time + edge_time + features_time)*1000:.1f}ms")
            print(f"  Enrichment: {enrich_time*1000:.1f}ms")
            
    finally:
        profiler.disable()
    
    # Print top time consumers
    print("\n" + "=" * 80)
    print("Top 20 functions by cumulative time:")
    print("=" * 80)
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    
    print("\n" + "=" * 80)
    print("Top 20 functions by total time:")
    print("=" * 80)
    stats.sort_stats("tottime")
    stats.print_stats(20)


if __name__ == "__main__":
    profile_enrichment()

