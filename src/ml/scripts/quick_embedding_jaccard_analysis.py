#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "pandas",
# "numpy",
# "gensim",
# ]
# ///
"""
Quick analysis: Compare embedding similarity to Jaccard similarity.

Simpler version that just computes correlation on a sample.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


try:
    import numpy as np
    import pandas as pd
    from gensim.models import KeyedVectors

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def compute_jaccard(pairs_df: pd.DataFrame, card1: str, card2: str) -> float:
    """Compute Jaccard similarity between two cards."""
    neighbors1 = set()
    neighbors2 = set()

    for _, row in pairs_df.iterrows():
        n1 = row.get("NAME_1", "")
        n2 = row.get("NAME_2", "")
    if n1 == card1:
        neighbors1.add(n2)

    elif n2 == card1:
        neighbors1.add(n1)
    if n1 == card2:
        neighbors2.add(n2)
    elif n2 == card2:
        neighbors2.add(n1)

    if not neighbors1 or not neighbors2:
        return 0.0

    intersection = len(neighbors1 & neighbors2)
    union = len(neighbors1 | neighbors2)
    return intersection / union if union > 0 else 0.0


def main() -> int:
    """Quick embedding vs Jaccard analysis."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding", type=Path, required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--test-set", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=10, help="Sample queries to analyze")

    args = parser.parse_args()

    if not HAS_DEPS:
        print("Error: pandas, numpy, gensim required")
        return 1

        print("Loading embedding...")
        embedding = KeyedVectors.load(str(args.embedding))

        print("Loading pairs (sampling 10000 rows)...")
        pairs_df = pd.read_csv(args.pairs, nrows=10000)

        print("Loading test set...")
        with open(args.test_set) as f:
            test_data = json.load(f)
        queries = list(test_data.get("queries", test_data).keys())[: args.sample]

        print(f"Analyzing {len(queries)} queries...")

        correlations = []
        overlaps = []

        for query in queries:
            if query not in embedding:
                continue

            # Get embedding top-20
            try:
                emb_similar = embedding.most_similar(query, topn=20)
                emb_cards = [c for c, _ in emb_similar]
            except KeyError:
                continue

            # Get Jaccard top-20 (sample from pairs)
            jaccard_scores = []
            seen = set()
            for _, row in pairs_df.iterrows():
                n1, n2 = row.get("NAME_1", ""), row.get("NAME_2", "")
                if n1 == query and n2 not in seen:
                    jaccard = compute_jaccard(pairs_df, query, n2)
                    jaccard_scores.append((n2, jaccard))
                    seen.add(n2)
                elif n2 == query and n1 not in seen:
                    jaccard = compute_jaccard(pairs_df, query, n1)
                    jaccard_scores.append((n1, jaccard))
                    seen.add(n1)
                if len(jaccard_scores) >= 20:
                    break

            jaccard_scores.sort(key=lambda x: x[1], reverse=True)
            jaccard_cards = [c for c, _ in jaccard_scores[:20]]

            # Overlap
            overlap = len(set(emb_cards[:10]) & set(jaccard_cards[:10]))
            overlaps.append(overlap / 10.0)

            # Correlation (for common cards)
            emb_dict = {c: s for c, s in emb_similar}
            jac_dict = {c: s for c, s in jaccard_scores}
            common = set(emb_cards) & set(jaccard_cards)

            if len(common) >= 5:
                emb_vals = [emb_dict.get(c, 0) for c in common]
                jac_vals = [jac_dict.get(c, 0) for c in common]
                corr = np.corrcoef(emb_vals, jac_vals)[0, 1]
                if not np.isnan(corr):
                    correlations.append(corr)

        result = {
            "avg_overlap": float(np.mean(overlaps)) if overlaps else 0.0,
            "avg_correlation": float(np.mean(correlations)) if correlations else 0.0,
            "n_queries": len(queries),
            "n_analyzed": len(overlaps),
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)

        print("\nResults:")
        print(f" Avg overlap (top-10): {result['avg_overlap']:.2%}")
        print(f" Avg correlation: {result['avg_correlation']:.4f}")

        if result["avg_overlap"] > 0.8:
            print("\nWarning: HIGH OVERLAP: Embeddings very similar to Jaccard")
            print(" Hypothesis: Embeddings learned co-occurrence (same as Jaccard)")
        elif result["avg_overlap"] > 0.5:
            print("\nWarning: MODERATE OVERLAP: Some difference from Jaccard")
        else:
            print("\n✓ LOW OVERLAP: Embeddings differ from Jaccard")

        return 0


if __name__ == "__main__":
    exit(main())
