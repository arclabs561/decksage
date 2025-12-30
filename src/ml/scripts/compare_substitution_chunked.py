#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""Compare embeddings in chunks with validation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gensim.models import KeyedVectors

# Embeddings to compare
embeddings_to_test = [
    ("functional", "data/embeddings/trained_functional.wv"),
    ("functional_improved", "data/embeddings/trained_functional_improved.wv"),
    ("functional_text", "data/embeddings/trained_functional_text.wv"),
    ("contrastive", "data/embeddings/trained_contrastive_substitution.wv"),
    ("heterogeneous", "data/embeddings/trained_heterogeneous_substitution.wv"),
]

# Load substitution pairs
pairs_path = Path("experiments/downstream_tests/substitution_magic_expanded_100.json")
with open(pairs_path) as f:
    pairs_data = json.load(f)

if isinstance(pairs_data, list):
    test_pairs = [tuple(p) if isinstance(p, (list, tuple)) else (p[0], p[1]) for p in pairs_data]
else:
    test_pairs = []

print(f"Comparing {len(embeddings_to_test)} embeddings on {len(test_pairs)} pairs")
print()

results = {}

# Process each embedding in chunks
for emb_name, emb_path in embeddings_to_test:
    emb_file = Path(emb_path)
    if not emb_file.exists():
        print(f"⏭️  {emb_name}: Not found, skipping")
        continue
    
    print(f"📊 Evaluating {emb_name}...")
    embedding = KeyedVectors.load(str(emb_file))
    
    # Evaluate in chunks
    chunk_size = 25
    chunk_results = []
    
    for i in range(0, len(test_pairs), chunk_size):
        chunk = test_pairs[i:i+chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (len(test_pairs) + chunk_size - 1) // chunk_size
        
        print(f"  Chunk {chunk_num}/{total_chunks}...", end=" ")
        
        found = 0
        ranks = []
        p_at_1 = 0
        p_at_5 = 0
        p_at_10 = 0
        
        for original, target in chunk:
            if original not in embedding:
                continue
            
            try:
                similar = embedding.most_similar(original, topn=50)
                predictions = [card for card, _ in similar]
                
                for rank, pred in enumerate(predictions, 1):
                    if pred == target:
                        ranks.append(rank)
                        found += 1
                        if rank <= 1:
                            p_at_1 += 1
                        if rank <= 5:
                            p_at_5 += 1
                        if rank <= 10:
                            p_at_10 += 1
                        break
            except Exception:
                continue
        
        chunk_p_at_10 = p_at_10 / len(chunk) if chunk else 0.0
        chunk_results.append({
            "found": found,
            "p_at_10_count": p_at_10,
            "total": len(chunk),
        })
        print(f"P@10={chunk_p_at_10:.3f} ({found}/{len(chunk)})")
    
    # Aggregate correctly
    total_found = sum(r["found"] for r in chunk_results)
    total_p_at_10_count = sum(r["p_at_10_count"] for r in chunk_results)
    total_pairs = sum(r["total"] for r in chunk_results)
    final_p_at_10 = total_p_at_10_count / total_pairs if total_pairs > 0 else 0.0
    
    results[emb_name] = {
        "p@10": final_p_at_10,
        "found": total_found,
        "total": total_pairs,
    }
    print(f"  ✅ {emb_name}: P@10={final_p_at_10:.3f}, Found={total_found}/{total_pairs}")
    print()

# Save results
output_path = Path("experiments/substitution_comparison_chunked.json")
with open(output_path, "w") as f:
    json.dump(results, f, indent=2)

print("=" * 70)
print("COMPARISON RESULTS")
print("=" * 70)
for name, result in sorted(results.items(), key=lambda x: x[1]["p@10"], reverse=True):
    print(f"{name:20s}: P@10={result['p@10']:.3f}, Found={result['found']}/{result['total']}")
print()
print(f"✅ Saved to {output_path}")
