#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Comprehensive comparison of all embedding variants.

Compares:
- Baseline (original embeddings)
- Functional embeddings
- Functional improved (tag Jaccard)
- Functional + text embeddings
- Jaccard baseline

Evaluates on:
- Similarity task (P@10, MRR)
- Substitution task (P@10)
- Deck completion (if available)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.scripts.evaluate_all_embeddings import (
        load_test_set,
        evaluate_embedding,
        evaluate_jaccard,
        load_graph_for_jaccard,
    )
    from ml.utils.name_normalizer import NameMapper
    HAS_EVAL = True
except ImportError:
    HAS_EVAL = False


EMBEDDINGS_TO_COMPARE = {
    "baseline": "data/embeddings/magic_128d_test_pecanpy.wv",
    "functional": "data/embeddings/trained_functional.wv",
    "functional_improved": "data/embeddings/trained_functional_improved.wv",
    "functional_text": "data/embeddings/trained_functional_text.wv",
}


def compare_embeddings(
    test_set_path: Path,
    pairs_csv: Path,
    name_mapping_path: Path | None = None,
    substitution_test_path: Path | None = None,
) -> dict[str, Any]:
    """Compare all embedding variants."""
    if not HAS_DEPS or not HAS_EVAL:
        print("❌ Missing dependencies")
        return {}
    
    print("=" * 70)
    print("COMPREHENSIVE EMBEDDING COMPARISON")
    print("=" * 70)
    print()
    
    # Load test set
    test_set = load_test_set(test_set_path)
    print(f"📊 Loaded test set: {len(test_set)} queries")
    
    # Load name mapping if available
    name_mapper = None
    if name_mapping_path and name_mapping_path.exists():
        try:
            with open(name_mapping_path) as f:
                mapping_data = json.load(f)
            name_mapper = NameMapper(mapping_data)
            print(f"  Loaded {len(name_mapper.mapping)} name mappings")
        except Exception as e:
            print(f"  ⚠️  Could not load name mapping: {e}")
    
    # Load Jaccard graph
    print("\n📊 Loading Jaccard graph...")
    jaccard_adj = load_graph_for_jaccard(pairs_csv)
    print(f"  Loaded {len(jaccard_adj)} cards")
    
    results = {
        "test_set": str(test_set_path),
        "similarity": {},
        "substitution": {},
    }
    
    # Evaluate Jaccard baseline
    print("\n" + "=" * 70)
    print("EVALUATING JACCARD BASELINE")
    print("=" * 70)
    jaccard_metrics = evaluate_jaccard(jaccard_adj, test_set, top_k=10, name_mapper=name_mapper)
    results["similarity"]["jaccard"] = jaccard_metrics
    print(f"  P@10: {jaccard_metrics['p@10']:.4f}, MRR: {jaccard_metrics['mrr']:.4f}, Queries: {jaccard_metrics['num_queries']}")
    
    # Evaluate each embedding
    for name, embed_path in EMBEDDINGS_TO_COMPARE.items():
        embed_file = Path(embed_path)
        if not embed_file.exists():
            print(f"\n⚠️  {name}: {embed_path} not found, skipping")
            continue
        
        print("\n" + "=" * 70)
        print(f"EVALUATING {name.upper()}")
        print("=" * 70)
        
        try:
            wv = KeyedVectors.load(str(embed_file))
            print(f"  Vocabulary: {len(wv)} cards")
            
            # Similarity evaluation
            metrics = evaluate_embedding(
                wv,
                test_set,
                top_k=10,
                name_mapper=name_mapper,
                per_query=False,
            )
            results["similarity"][name] = metrics
            print(f"  P@10: {metrics['p@10']:.4f}, MRR: {metrics['mrr']:.4f}, Queries: {metrics['num_queries']}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue
    
    # Substitution evaluation if available
    if substitution_test_path and substitution_test_path.exists():
        print("\n" + "=" * 70)
        print("EVALUATING SUBSTITUTION TASK")
        print("=" * 70)
        
        with open(substitution_test_path) as f:
            sub_data = json.load(f)
        
        # Handle both dict and list formats
        if isinstance(sub_data, dict):
            sub_pairs = sub_data.get("pairs", [])
        elif isinstance(sub_data, list):
            sub_pairs = sub_data
        else:
            sub_pairs = []
        
        print(f"  Test pairs: {len(sub_pairs)}")
        
        # Evaluate substitution for each embedding
        for name, embed_path in EMBEDDINGS_TO_COMPARE.items():
            embed_file = Path(embed_path)
            if not embed_file.exists():
                continue
            
            try:
                wv = KeyedVectors.load(str(embed_file))
                
                found = 0
                ranks = []
                
                for pair in sub_pairs[:50]:  # Limit for speed
                    # Handle both dict and list formats
                    if isinstance(pair, dict):
                        query = pair.get("query", "")
                        target = pair.get("target", "")
                    elif isinstance(pair, list) and len(pair) >= 2:
                        query = str(pair[0])
                        target = str(pair[1])
                    else:
                        continue
                    
                    if query not in wv or target not in wv:
                        continue
                    
                    # Get top 10 similar
                    try:
                        similar = wv.most_similar(query, topn=10)
                        similar_cards = [card for card, _ in similar]
                        
                        if target in similar_cards:
                            found += 1
                            rank = similar_cards.index(target) + 1
                            ranks.append(rank)
                    except Exception:
                        continue
                
                p10 = found / len(sub_pairs) if sub_pairs else 0.0
                avg_rank = sum(ranks) / len(ranks) if ranks else 0.0
                
                results["substitution"][name] = {
                    "p@10": p10,
                    "found": found,
                    "total": len(sub_pairs),
                    "avg_rank": avg_rank,
                }
                print(f"  {name}: P@10={p10:.4f}, Found={found}/{len(sub_pairs)}, AvgRank={avg_rank:.1f}")
                
            except Exception as e:
                print(f"  {name}: Error - {e}")
                continue
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare all embedding variants")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--pairs-csv", type=str, required=True, help="Pairs CSV for Jaccard")
    parser.add_argument("--name-mapping", type=str, help="Name mapping JSON")
    parser.add_argument("--substitution-test", type=str, help="Substitution test JSON")
    parser.add_argument("--output", type=str, required=True, help="Output JSON")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    results = compare_embeddings(
        test_set_path=Path(args.test_set),
        pairs_csv=Path(args.pairs_csv),
        name_mapping_path=Path(args.name_mapping) if args.name_mapping else None,
        substitution_test_path=Path(args.substitution_test) if args.substitution_test else None,
    )
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if "similarity" in results:
        print("\n📊 SIMILARITY TASK:")
        for method, metrics in results["similarity"].items():
            p10 = metrics.get("p@10", 0.0)
            mrr = metrics.get("mrr", 0.0)
            queries = metrics.get("num_queries", 0)
            print(f"  {method:20s} P@10={p10:.4f}  MRR={mrr:.4f}  Queries={queries}")
    
    if "substitution" in results:
        print("\n📊 SUBSTITUTION TASK:")
        for method, metrics in results["substitution"].items():
            p10 = metrics.get("p@10", 0.0)
            found = metrics.get("found", 0)
            total = metrics.get("total", 0)
            print(f"  {method:20s} P@10={p10:.4f}  Found={found}/{total}")
    
    print(f"\n✅ Results saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

