#!/usr/bin/env python3
"""
exp_010-013: Compare Multiple Embedding Methods

Run in parallel:
- exp_010: DeepWalk (p=1, q=1, simpler than Node2Vec)
- exp_011: Node2Vec with tuned p,q (p=2, q=0.5 - BFS bias)
- exp_012: Node2Vec with DFS bias (p=0.5, q=2)
- exp_013: Ensemble (average of all methods)

All use same 500-deck graph for fair comparison.
"""

import json

import pandas as pd
from gensim.models import Word2Vec
from pecanpy.pecanpy import SparseOTF

# Use PATHS for canonical paths
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.paths import PATHS


def prepare_edgelist(csv_file, output_edg):
    """Convert to PecanPy format"""
    df = pd.read_csv(csv_file)

    with open(output_edg, "w") as f:
        for _, row in df.iterrows():
            f.write(f"{row['NAME_1']}\t{row['NAME_2']}\t{row['COUNT_MULTISET']}\n")

    num_nodes = len(set(df["NAME_1"]) | set(df["NAME_2"]))
    return num_nodes, len(df)


def train_embedding(edg_file, output_file, p=1.0, q=1.0, dim=128, name="node2vec"):
    """Train embedding with given p,q"""
    print(f"\n{name} (p={p}, q={q}):")
    print("  Generating walks...")

    g = SparseOTF(p=p, q=q, workers=8, verbose=False, extend=True)
    g.read_edg(edg_file, weighted=True, directed=False)
    walks = g.simulate_walks(num_walks=10, walk_length=80)

    print("  Training Word2Vec...")
    model = Word2Vec(walks, vector_size=dim, window=10, min_count=0, sg=1, workers=8, epochs=1)
    model.wv.save(output_file)

    print(f"  ✓ Saved: {output_file}")
    return model.wv


def evaluate_on_queries(wv, queries):
    """Quick eval on test queries"""
    for query in queries[:3]:  # Just first 3 for speed
        if query in wv:
            results = wv.most_similar(query, topn=3)
            print(f"    {query}: {results[0][0]}")


def main():
    print("=" * 60)
    print("exp_010-013: Multiple Embedding Methods")
    print("=" * 60)

    # Prepare data using PATHS
    edg_file = str(PATHS.graphs / "magic_500decks.edg")
    num_nodes, num_edges = prepare_edgelist(str(PATHS.pairs_500), edg_file)
    print(f"\nGraph: {num_nodes:,} nodes, {num_edges:,} edges")

    test_queries = ["Lightning Bolt", "Brainstorm", "Sol Ring", "Counterspell"]

    # exp_010: DeepWalk (p=1, q=1)
    wv_deepwalk = train_embedding(
        edg_file, str(PATHS.embedding("deepwalk")), p=1.0, q=1.0, name="DeepWalk"
    )
    evaluate_on_queries(wv_deepwalk, test_queries)

    # exp_011: Node2Vec BFS (p=2, q=0.5)
    wv_bfs = train_embedding(
        edg_file, str(PATHS.embedding("node2vec_bfs")), p=2.0, q=0.5, name="Node2Vec-BFS"
    )
    evaluate_on_queries(wv_bfs, test_queries)

    # exp_012: Node2Vec DFS (p=0.5, q=2.0)
    wv_dfs = train_embedding(
        edg_file, str(PATHS.embedding("node2vec_dfs")), p=0.5, q=2.0, name="Node2Vec-DFS"
    )
    evaluate_on_queries(wv_dfs, test_queries)

    # exp_013: Default Node2Vec (p=1, q=1)
    wv_default = train_embedding(
        edg_file, str(PATHS.embedding("node2vec_default")), p=1.0, q=1.0, name="Node2Vec-Default"
    )
    evaluate_on_queries(wv_default, test_queries)

    # Log all
    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        for exp_id, method, p, q in [
            ("exp_010", "DeepWalk", 1.0, 1.0),
            ("exp_011", "Node2Vec-BFS", 2.0, 0.5),
            ("exp_012", "Node2Vec-DFS", 0.5, 2.0),
            ("exp_013", "Node2Vec-Default", 1.0, 1.0),
        ]:
            exp = {
                "experiment_id": exp_id,
                "date": "2025-10-01",
                "phase": "hyperparameter_search",
                "hypothesis": f"{method} with p={p}, q={q} might work better than default",
                "method": f"{method} (p={p}, q={q}, dim=128)",
                "data": "500 MTG decks",
                "results": {"saved": True, "eval": "pending"},
                "next_steps": ["Evaluate on diverse queries", "Compare all 4 methods"],
            }
            f.write(json.dumps(exp) + "\n")

    print("\n✓ Logged exp_010-013")
    print("\nNext: Compare all 4 embeddings on same test set")


if __name__ == "__main__":
    main()
