#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["nodevectors", "gensim>=4.3.0", "numpy<2.0.0", "sentence-transformers>=2.2.0"]
# ///
"""
Train ProNE embeddings as a fast structural baseline.

ProNE (Fast and Scalable Network Representation Learning, IJCAI 2019)
uses randomized SVD + spectral propagation. 10-100x faster than node2vec.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/training/train_prone.py \
        --edgelist data/graphs/pokemon_blended.edg \
        --output data/embeddings/pokemon_prone.wv \
        --dim 128
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.data_loading import load_edgelist


def main():
    parser = argparse.ArgumentParser(description="Train ProNE embeddings")
    parser.add_argument("--edgelist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--max-edges", type=int, default=0,
                        help="Subsample to top-K weighted edges (0=no limit)")
    parser.add_argument("--card-attributes", type=Path, default=None,
                        help="Card attributes CSV for cold-start text embeddings. "
                             "Cards with zero/few graph edges get initialized from "
                             "oracle text embeddings (all-MiniLM-L6-v2).")
    parser.add_argument("--cold-start-threshold", type=int, default=3,
                        help="Nodes with <= this many edges get text-based init (default: 3)")
    args = parser.parse_args()

    print(f"Loading edgelist from {args.edgelist}...")
    edges, nodes = load_edgelist(args.edgelist, collect_nodes=True)
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    if args.max_edges > 0 and len(edges) > args.max_edges:
        print(f"  Subsampling to top {args.max_edges} edges by weight...")
        edges.sort(key=lambda x: -x[2])
        edges = edges[:args.max_edges]
        nodes = set()
        for n1, n2, _ in edges:
            nodes.add(n1)
            nodes.add(n2)
        print(f"  After subsampling: {len(nodes)} nodes, {len(edges)} edges")

    # Build node index
    node_list = sorted(nodes)
    node_to_idx = {n: i for i, n in enumerate(node_list)}

    # Build CSR graph for ProNE
    import scipy.sparse as sp
    rows, cols, weights = [], [], []
    for n1, n2, w in edges:
        i, j = node_to_idx[n1], node_to_idx[n2]
        rows.extend([i, j])
        cols.extend([j, i])
        weights.extend([w, w])

    adj = sp.csr_matrix((weights, (rows, cols)), shape=(len(node_list), len(node_list)))

    print(f"Training ProNE (dim={args.dim})...")
    t0 = time.time()

    import nodevectors
    model = nodevectors.ProNE(n_components=args.dim)
    model.fit(adj)

    elapsed = time.time() - t0
    print(f"  Trained in {elapsed:.1f}s")

    # Extract embeddings: model.model is a dict {node_idx: embedding_array}
    actual_dim = len(model.model[0])
    embeddings = np.array([model.model[i] for i in range(len(node_list))], dtype=np.float32)

    # Cold-start: replace embeddings for low-degree nodes with text-based init
    if args.card_attributes and args.card_attributes.exists():
        import csv

        from sklearn.decomposition import PCA

        print(f"\nCold-start init from {args.card_attributes.name}...")

        # Load oracle text
        card_texts: dict[str, str] = {}
        with open(args.card_attributes, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                text = row.get("oracle_text", "").strip()
                if name and text and text != "nan":
                    card_texts[name] = f"{name}. {row.get('type', '')}. {text}"

        # Find low-degree nodes
        node_degree = np.zeros(len(node_list))
        for n1, n2, _ in edges:
            node_degree[node_to_idx[n1]] += 1
            node_degree[node_to_idx[n2]] += 1

        cold_indices = []
        cold_texts = []
        for idx, name in enumerate(node_list):
            if node_degree[idx] <= args.cold_start_threshold and name in card_texts:
                cold_indices.append(idx)
                cold_texts.append(card_texts[name])

        if cold_texts:
            from sentence_transformers import SentenceTransformer

            st_model = SentenceTransformer("all-MiniLM-L6-v2")
            text_embs = st_model.encode(
                cold_texts, batch_size=256, show_progress_bar=False,
                convert_to_numpy=True, normalize_embeddings=True,
            )
            # Project 384-dim -> target dim via PCA
            if text_embs.shape[1] != actual_dim:
                pca = PCA(n_components=actual_dim)
                text_embs = pca.fit_transform(text_embs)

            # Replace cold-start node embeddings
            for i, idx in enumerate(cold_indices):
                embeddings[idx] = text_embs[i].astype(np.float32)

            print(f"  {len(cold_indices)} cold-start nodes initialized from text "
                  f"(degree <= {args.cold_start_threshold})")
        else:
            print("  No cold-start candidates found (all nodes have sufficient edges or no text)")

    # Save as KeyedVectors
    kv = KeyedVectors(vector_size=actual_dim)
    kv.add_vectors(node_list, embeddings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    kv.save(str(args.output))
    print(f"Saved {len(node_list)} embeddings to {args.output}")

    # Quality check
    from sklearn.preprocessing import normalize
    emb_norm = normalize(embeddings, norm='l2')
    rng = np.random.default_rng(42)
    n_pairs = min(10000, len(node_list) * (len(node_list) - 1) // 2)
    sims = []
    for _ in range(n_pairs):
        i, j = rng.choice(len(node_list), 2, replace=False)
        sims.append(np.dot(emb_norm[i], emb_norm[j]))
    sims_arr = np.array(sims)
    print(f"  Random-pair cosine sim: mean={sims_arr.mean():.4f}, std={sims_arr.std():.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
