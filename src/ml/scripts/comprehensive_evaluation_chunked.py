#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""Comprehensive evaluation in chunks with validation."""

import json
import sys
from pathlib import Path

from ml.utils.path_setup import setup_project_paths
from ml.utils.paths import PATHS

setup_project_paths()
from gensim.models import KeyedVectors

# Embeddings to evaluate
embeddings = {
    "functional": PATHS.embeddings / "trained_functional.wv",
    "functional_improved": PATHS.embeddings / "trained_functional_improved.wv",
    "functional_text": PATHS.embeddings / "trained_functional_text.wv",
    "contrastive": PATHS.embeddings / "trained_contrastive_substitution.wv",
}

# Load test set
test_set_path = PATHS.test_magic
with open(test_set_path) as f:
    test_data = json.load(f)
test_queries = test_data.get("queries", test_data) if isinstance(test_data, dict) else test_data

print(f"Evaluating on {len(test_queries)} queries")
print()

results = {}

# Evaluate each embedding in chunks
for emb_name, emb_path in embeddings.items():
    emb_file = Path(emb_path)
    if not emb_file.exists():
        print(f"⏭️ {emb_name}: Not found, skipping")
        continue

    print(f" Evaluating {emb_name}...")
    embedding = KeyedVectors.load(str(emb_file))

    # Evaluate in chunks
    chunk_size = 25
    queries_list = list(test_queries.items())
    total_p_at_10 = 0
    total_found = 0

    for i in range(0, len(queries_list), chunk_size):
        chunk = queries_list[i:i+chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (len(queries_list) + chunk_size - 1) // chunk_size
        print(f" Chunk {chunk_num}/{total_chunks}...", end=" ")

        chunk_p_at_10 = 0
        chunk_found = 0

        for query, labels in chunk:
            if query not in embedding:
                continue

            # Get relevant cards
            relevant = (
                labels.get("highly_relevant", []) +
                labels.get("relevant", []) +
                labels.get("somewhat_relevant", [])
            )
            if not relevant:
                continue

            try:
                similar = embedding.most_similar(query, topn=10)
                predictions = [card for card, _ in similar]

                # Check if any relevant card is in top 10
                for pred in predictions:
                    if pred in relevant:
                        chunk_p_at_10 += 1
                        chunk_found += 1
                        break
            except Exception:
                continue

        chunk_p_at_10_rate = chunk_p_at_10 / len(chunk) if chunk else 0.0
        total_p_at_10 += chunk_p_at_10
        total_found += chunk_found
        print(f"P@10={chunk_p_at_10_rate:.3f} ({chunk_found}/{len(chunk)})")

    final_p_at_10 = total_p_at_10 / len(queries_list) if queries_list else 0.0
    results[emb_name] = {
        "p@10": final_p_at_10,
        "found": total_found,
        "total": len(queries_list),
    }
    print(f" {emb_name}: P@10={final_p_at_10:.3f}, Found={total_found}/{len(queries_list)}")
    print()

# Save results
output_path = PATHS.experiments / "comprehensive_evaluation_chunked.json"
with open(output_path, "w") as f:
    json.dump(results, f, indent=2)

print("=" * 70)
print("COMPREHENSIVE EVALUATION RESULTS")
print("=" * 70)
for name, result in sorted(results.items(), key=lambda x: x[1]["p@10"], reverse=True):
    print(f"{name:20s}: P@10={result['p@10']:.3f} ({result['found']}/{result['total']})")
print()
print(f" Saved to {output_path}")
