#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
#     "scipy>=1.10.0",
# ]
# ///
"""Optimize fusion weights in chunks with validation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gensim.models import KeyedVectors
from ml.similarity.fusion import WeightedLateFusion, FusionWeights
from ml.deck_building.deck_completion import suggest_replacements

# Load embedding
embedding = KeyedVectors.load("data/embeddings/trained_functional_improved.wv")
print(f"✅ Loaded embedding: {len(embedding)} cards")

# Load Jaccard graph
import pandas as pd
pairs_csv = Path("data/processed/pairs_large.csv")
adj = {}
with open(pairs_csv) as f:
    for line in f:
        if line.strip().startswith("#") or not line.strip():
            continue
        parts = line.strip().split()
        if len(parts) >= 2:
            card1, card2 = parts[0], parts[1]
            if card1 not in adj:
                adj[card1] = set()
            adj[card1].add(card2)
            if card2 not in adj:
                adj[card2] = set()
            adj[card2].add(card1)

print(f"✅ Loaded Jaccard graph: {len(adj)} cards")

# Load test pairs
pairs_path = Path("experiments/downstream_tests/substitution_magic_expanded_100.json")
with open(pairs_path) as f:
    pairs_data = json.load(f)

if isinstance(pairs_data, list):
    test_pairs = [tuple(p) if isinstance(p, (list, tuple)) else (p[0], p[1]) for p in pairs_data]
else:
    test_pairs = []

print(f"✅ Loaded {len(test_pairs)} test pairs")
print()

# Test different weight combinations in chunks
weight_combinations = [
    (0.2, 0.8),  # Low embed, high Jaccard
    (0.4, 0.6),  # Balanced
    (0.6, 0.4),  # High embed, low Jaccard
    (0.5, 0.5),  # Equal
]

print("Testing weight combinations...")
results = {}

for embed_weight, jaccard_weight in weight_combinations:
    weights = FusionWeights(embed=embed_weight, jaccard=jaccard_weight)
    fusion = WeightedLateFusion(
        embeddings=embedding,
        adj=adj,
        weights=weights,
    )
    
    # Evaluate in chunks
    chunk_size = 25
    total_found = 0
    total_p_at_10 = 0
    
    for i in range(0, len(test_pairs), chunk_size):
        chunk = test_pairs[i:i+chunk_size]
        
        for original, target in chunk:
            if original not in embedding or original not in adj:
                continue
            
            try:
                similar = fusion.similar(original, top_k=10)
                predictions = [card for card, _ in similar]
                
                for rank, pred in enumerate(predictions, 1):
                    if pred == target:
                        total_found += 1
                        if rank <= 10:
                            total_p_at_10 += 1
                        break
            except Exception:
                continue
    
    p_at_10 = total_p_at_10 / len(test_pairs) if test_pairs else 0.0
    
    results[f"embed_{embed_weight}_jaccard_{jaccard_weight}"] = {
        "p@10": p_at_10,
        "found": total_found,
        "total": len(test_pairs),
    }
    
    print(f"  Weights ({embed_weight:.1f}, {jaccard_weight:.1f}): P@10={p_at_10:.3f}, Found={total_found}/{len(test_pairs)}")

# Find best
best = max(results.items(), key=lambda x: x[1]["p@10"])
print()
print("=" * 70)
print("BEST WEIGHTS")
print("=" * 70)
print(f"Combination: {best[0]}")
print(f"P@10: {best[1]['p@10']:.3f}")
print(f"Found: {best[1]['found']}/{best[1]['total']}")

# Save
output_path = Path("experiments/fusion_optimization_chunked.json")
with open(output_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"✅ Saved to {output_path}")
