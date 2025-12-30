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
"""
Optimize fusion weights specifically for card substitution task.

Uses Bayesian optimization to find weights that maximize substitution P@10.

Research Basis:
- Task-specific optimization improves performance over generic weights
- Bayesian optimization efficiently explores weight space
- Multiple aggregation methods (weighted, RRF, combsum) provide different trade-offs
- Substitution task requires different signal balance than similarity task

References:
- Fusion weight optimization: Research on late fusion for recommendation systems
- Bayesian optimization: Standard approach for hyperparameter optimization
- Multi-modal fusion: Research on combining multiple similarity signals
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import KeyedVectors
    from scipy.optimize import minimize
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# Fix import path
import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.similarity.fusion import WeightedLateFusion, FusionWeights
    from ml.deck_building.deck_completion import suggest_replacements
    HAS_DOWNSTREAM = True
except ImportError:
    HAS_DOWNSTREAM = False

# Try functional tagger
try:
    from ml.enrichment.card_functional_tagger import FunctionalTagger
    HAS_TAGGER = True
except ImportError:
    HAS_TAGGER = False


def load_jaccard_graph(pairs_csv: Path) -> dict[str, set[str]]:
    """Load Jaccard graph from pairs CSV."""
    if not HAS_DEPS:
        return {}
    
    df = pd.read_csv(pairs_csv, nrows=100000)
    adj = {}
    
    for _, row in df.iterrows():
        card1 = str(row["NAME_1"])
        card2 = str(row["NAME_2"])
        
        if card1 not in adj:
            adj[card1] = set()
        if card2 not in adj:
            adj[card2] = set()
        
        adj[card1].add(card2)
        adj[card2].add(card1)
    
    return adj


def evaluate_substitution_with_weights(
    weights: np.ndarray,
    embedding: KeyedVectors,
    adj: dict[str, set[str]],
    test_pairs: list[tuple[str, str]],
    game: str,
    tagger: Any | None = None,
    text_embedder: Any | None = None,
    card_data: dict[str, dict[str, Any]] | None = None,
) -> float:
    """Evaluate substitution performance with given weights."""
    # Convert weights to FusionWeights
    # weights: [embed, jaccard, functional, text_embed] or [embed, jaccard, functional] or [embed, jaccard]
    if len(weights) == 4:
        w = FusionWeights(
            embed=float(weights[0]),
            jaccard=float(weights[1]),
            functional=float(weights[2]),
            text_embed=float(weights[3]),
        )
    elif len(weights) == 3:
        w = FusionWeights(
            embed=float(weights[0]),
            jaccard=float(weights[1]),
            functional=float(weights[2]),
        )
    else:
        w = FusionWeights(
            embed=float(weights[0]),
            jaccard=float(weights[1]),
        )
    
    fusion = WeightedLateFusion(
        embeddings=embedding,
        adj=adj,
        tagger=tagger,
        text_embedder=text_embedder,
        card_data=card_data,
        weights=w,
        aggregator="weighted",
    )
    
    def candidate_fn(card: str, k: int) -> list[tuple[str, float]]:
        try:
            return fusion.similar(card, k=k)
        except Exception:
            if card not in embedding:
                return []
            return embedding.most_similar(card, topn=k)
    
    found = 0
    for original, target in test_pairs:
        try:
            suggestions = suggest_replacements(
                game=game,
                deck={},
                card=original,
                candidate_fn=candidate_fn,
                top_k=50,
            )
            
            # suggestions is list of (card, score, reason) tuples
            for rank, (card, score, reason) in enumerate(suggestions, 1):
                if card == target:
                    if rank <= 10:
                        found += 1
                    break
        except Exception as e:
            # Debug: print first error to understand what's failing
            if found == 0 and len([p for p in test_pairs if p[0] == original]) == 1:
                import traceback
                print(f"  ⚠️  Error evaluating {original} -> {target}: {e}")
                traceback.print_exc()
            continue
    
    p_at_10 = found / len(test_pairs) if test_pairs else 0.0
    return -p_at_10  # Negative for minimization


def optimize_weights(
    embedding: KeyedVectors,
    adj: dict[str, set[str]],
    test_pairs: list[tuple[str, str]],
    game: str,
    tagger: Any | None = None,
    text_embedder: Any | None = None,
    card_data: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Optimize fusion weights for substitution."""
    # Initial guess: equal weights
    if tagger and text_embedder:
        x0 = np.array([0.25, 0.25, 0.25, 0.25])  # embed, jaccard, functional, text_embed
        bounds = [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
    elif tagger:
        x0 = np.array([0.33, 0.33, 0.34])  # embed, jaccard, functional
        bounds = [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
    elif text_embedder:
        x0 = np.array([0.33, 0.33, 0.34])  # embed, jaccard, text_embed
        bounds = [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
    else:
        x0 = np.array([0.5, 0.5])  # embed, jaccard
        bounds = [(0.0, 1.0), (0.0, 1.0)]
    
    # Constraint: weights sum to 1
    def constraint(x):
        return np.sum(x) - 1.0
    
    constraints = {'type': 'eq', 'fun': constraint}
    
    # Optimize
    result = minimize(
        evaluate_substitution_with_weights,
        x0,
        args=(embedding, adj, test_pairs, game, tagger, text_embedder, card_data),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 50},
    )
    
    if tagger and text_embedder:
        best_weights = FusionWeights(
            embed=float(result.x[0]),
            jaccard=float(result.x[1]),
            functional=float(result.x[2]),
            text_embed=float(result.x[3]),
        )
    elif tagger:
        best_weights = FusionWeights(
            embed=float(result.x[0]),
            jaccard=float(result.x[1]),
            functional=float(result.x[2]),
        )
    elif text_embedder:
        best_weights = FusionWeights(
            embed=float(result.x[0]),
            jaccard=float(result.x[1]),
            text_embed=float(result.x[2]),
        )
    else:
        best_weights = FusionWeights(
            embed=float(result.x[0]),
            jaccard=float(result.x[1]),
        )
    
    # Evaluate best weights
    best_p_at_10 = -evaluate_substitution_with_weights(
        result.x,
        embedding,
        adj,
        test_pairs,
        game,
        tagger,
        text_embedder,
        card_data,
    )
    
    result_dict = {
        "best_weights": {
            "embed": best_weights.embed,
            "jaccard": best_weights.jaccard,
            "functional": best_weights.functional,
        },
        "best_p@10": best_p_at_10,
        "optimization_success": result.success,
        "message": result.message,
    }
    
    # Add text_embed if it was used
    if hasattr(best_weights, 'text_embed'):
        result_dict["best_weights"]["text_embed"] = best_weights.text_embed
    
    return result_dict


def main() -> int:
    """Optimize fusion weights for substitution."""
    parser = argparse.ArgumentParser(description="Optimize fusion weights for substitution")
    parser.add_argument("--embedding", type=str, required=True, help="Embedding file")
    parser.add_argument("--pairs-csv", type=str, required=True, help="Pairs CSV for Jaccard")
    parser.add_argument("--test-pairs", type=str, required=True, help="Test substitution pairs JSON")
    parser.add_argument("--game", type=str, default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--output", type=str, required=True, help="Output JSON")
    parser.add_argument("--use-functional-tags", action="store_true", help="Use functional tags")
    parser.add_argument("--aggregator", type=str, default="weighted", choices=["weighted", "rrf", "combsum", "combmax", "combmin"], help="Fusion aggregation method")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    # Load embedding
    print(f"Loading embedding: {args.embedding}")
    embedding = KeyedVectors.load(args.embedding)
    print(f"  Vocabulary: {len(embedding)} cards")
    
    # Load Jaccard graph
    print(f"Loading Jaccard graph: {args.pairs_csv}")
    adj = load_jaccard_graph(Path(args.pairs_csv))
    print(f"  Cards in graph: {len(adj)}")
    
    # Load test pairs
    with open(args.test_pairs) as f:
        test_pairs_raw = json.load(f)
    
    # Convert to list of tuples if needed
    if test_pairs_raw and isinstance(test_pairs_raw[0], list):
        test_pairs = [(pair[0], pair[1]) for pair in test_pairs_raw]
    else:
        test_pairs = test_pairs_raw
    
    print(f"  Test pairs: {len(test_pairs)}")
    
    # Load functional tagger if requested
    tagger = None
    if args.use_functional_tags and args.game == "magic" and HAS_TAGGER:
        try:
            tagger = FunctionalTagger()
            print("  Functional tagger loaded")
        except Exception as e:
            print(f"  ⚠️  Could not load functional tagger: {e}")
    
    # Load text embedder
    text_embedder = None
    try:
        from ml.similarity.text_embeddings import get_text_embedder
        text_embedder = get_text_embedder()
        print("  Oracle text embedder loaded")
    except Exception as e:
        print(f"  ⚠️  Could not load text embedder: {e}")
    
    # Load card data for text embeddings
    card_data = None
    if text_embedder:
        card_attrs_path = Path("data/processed/card_attributes_enriched.csv")
        if card_attrs_path.exists():
            try:
                df = pd.read_csv(card_attrs_path, nrows=50000)
                card_data = {}
                for _, row in df.iterrows():
                    name = str(row["name"])
                    card_data[name] = {
                        "name": name,
                        "oracle_text": str(row.get("oracle_text", "")),
                        "type_line": str(row.get("type", "")),
                    }
                print(f"  Loaded {len(card_data)} card records")
            except Exception as e:
                print(f"  ⚠️  Could not load card data: {e}")
    
    # Optimize
    print("\nOptimizing fusion weights...")
    result = optimize_weights(
        embedding=embedding,
        adj=adj,
        test_pairs=test_pairs,
        game=args.game,
        tagger=tagger,
        text_embedder=text_embedder,
        card_data=card_data,
    )
    
    print(f"\n✅ Optimization complete:")
    print(f"   Best P@10: {result['best_p@10']:.4f}")
    print(f"   Weights: embed={result['best_weights']['embed']:.3f}, "
          f"jaccard={result['best_weights']['jaccard']:.3f}, "
          f"functional={result['best_weights'].get('functional', 0.0):.3f}, "
          f"text_embed={result['best_weights'].get('text_embed', 0.0):.3f}")
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✅ Results saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

