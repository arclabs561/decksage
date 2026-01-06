#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.0.0",
# ]
# ///
"""
Optimize fusion weights based on available signals.

This script:
1. Checks which signals are actually available
2. Runs grid search only over available signals
3. Saves optimized weights for use in API
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from gensim.models import KeyedVectors
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_graph
from ml.utils.data_loading import load_test_set
from ml.utils.paths import PATHS


def check_available_signals(
    embeddings_path: Path,
    pairs_path: Path | None = None,
    card_attrs_path: Path | None = None,
) -> dict[str, bool]:
    """Check which signals are available, including visual embeddings."""
    signals = {
        "embeddings": False,
        "graph_data": False,
        "functional_tagger": False,
        "text_embedder": False,
        "visual_embedder": False,
        "card_attrs": False,
        "gnn_embedder": False,
    }
    
    # Check embeddings
    if embeddings_path.exists():
        try:
            _ = KeyedVectors.load(str(embeddings_path))
            signals["embeddings"] = True
        except Exception:
            pass
    
    # Check graph data
    if pairs_path and pairs_path.exists():
        try:
            _, _ = load_graph(str(pairs_path), filter_lands=True)
            signals["graph_data"] = True
        except Exception:
            pass
    
    # Check functional tagger
    try:
        from ml.enrichment.card_functional_tagger import FunctionalTagger
        _ = FunctionalTagger()
        signals["functional_tagger"] = True
    except Exception:
        pass
    
    # Check text embedder
    try:
        from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
        # Just check if we can import, actual loading happens later
        signals["text_embedder"] = True
    except Exception:
        pass
    
    # Check visual embedder
    try:
        from ml.similarity.visual_embeddings import get_visual_embedder
        # Just check if we can import, actual loading happens later
        signals["visual_embedder"] = True
    except Exception:
        pass
    
    # Check card attrs
    if card_attrs_path and card_attrs_path.exists():
        signals["card_attrs"] = True
    
    # Check GNN (optional)
    gnn_path = PATHS.embeddings / "gnn_graphsage.json"
    if not gnn_path.exists():
        gnn_path = PATHS.experiments / "signals" / "gnn_graphsage.json"
    if gnn_path.exists():
        signals["gnn_embedder"] = True
    
    return signals


def create_fusion_builder(
    embeddings: KeyedVectors,
    adj: dict[str, set[str]] | None,
    signals: dict[str, bool],
    card_attrs: dict | None = None,
) -> callable:
    """Create a fusion builder function for grid search."""
    
    # Load tagger if available
    tagger = None
    if signals["functional_tagger"]:
        try:
            from ml.enrichment.card_functional_tagger import FunctionalTagger
            tagger = FunctionalTagger()
        except Exception:
            pass
    
    # Load text embedder if available
    text_embedder = None
    if signals["text_embedder"] and card_attrs:
        try:
            from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
            text_embedder = InstructionTunedCardEmbedder(model_name="intfloat/e5-base-v2")
        except Exception:
            pass
    
    # Load visual embedder if available
    visual_embedder = None
    if signals["visual_embedder"]:
        try:
            from ml.similarity.visual_embeddings import get_visual_embedder
            visual_embedder = get_visual_embedder()
        except Exception:
            pass
    
    def builder(weights: FusionWeights) -> WeightedLateFusion:
        return WeightedLateFusion(
            embeddings=embeddings,
            adj=adj or {},
            tagger=tagger,
            weights=weights,
            text_embedder=text_embedder,
            visual_embedder=visual_embedder,
            card_data=card_attrs or {},
        )
    
    return builder


def grid_search_available_signals(
    fusion_builder: callable,
    test_set: dict,
    signals: dict[str, bool],
    step: float = 0.1,
    top_k: int = 10,
) -> dict:
    """Run grid search only over available signals."""
    
    # Determine which weights to optimize
    active_weights = []
    if signals["embeddings"]:
        active_weights.append("embed")
    if signals["graph_data"]:
        active_weights.append("jaccard")
    if signals["functional_tagger"]:
        active_weights.append("functional")
    if signals["text_embedder"]:
        active_weights.append("text_embed")
    if signals["visual_embedder"]:
        active_weights.append("visual_embed")
    if signals["gnn_embedder"]:
        active_weights.append("gnn")
    
    print(f"Optimizing weights for: {', '.join(active_weights)}")
    
    # Simple grid search: equal weights for available signals
    # More sophisticated search can be added later
    best_score = -1.0
    best_weights = None
    results = []
    
    # Try equal weights first
    if len(active_weights) > 0:
        equal_weight = 1.0 / len(active_weights)
        weights_dict = {w: 0.0 for w in ["embed", "jaccard", "functional", "text_embed", "gnn"]}
        for w in active_weights:
            weights_dict[w] = equal_weight
        
        weights = FusionWeights(**weights_dict).normalized()
        fusion = fusion_builder(weights)
        
        # Convert test set to flat format (dict[str, list[str]])
        flat_test_set = {}
        for query, labels in test_set.items():
            if isinstance(labels, dict):
                # Combine all relevant cards (excluding irrelevant)
                all_relevant = []
                for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
                    all_relevant.extend(labels.get(level, []))
                if all_relevant:
                    flat_test_set[query] = all_relevant
            else:
                # Already flat format
                flat_test_set[query] = labels if isinstance(labels, list) else []
        
        # Evaluate using direct precision calculation
        from ml.utils.evaluation import compute_precision_at_k
        
        scores = []
        evaluated = 0
        skipped = 0
        
        for query, labels in test_set.items():
            try:
                # Get predictions
                predictions = fusion.similar(query, top_k)
                if not predictions:
                    skipped += 1
                    continue
                
                # Extract card names from predictions
                pred_cards = [card for card, _ in predictions]
                
                # Convert labels to dict format expected by compute_precision_at_k
                if isinstance(labels, dict):
                    labels_dict = labels  # Already in correct format
                else:
                    # Convert flat list to dict format
                    labels_dict = {
                        "highly_relevant": labels if isinstance(labels, list) else [],
                        "relevant": [],
                        "somewhat_relevant": [],
                        "marginally_relevant": [],
                        "irrelevant": [],
                    }
                
                # Compute P@K
                p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=top_k)
                scores.append(p_at_k)
                evaluated += 1
                
            except Exception as e:
                skipped += 1
                if evaluated < 5:  # Only print first few errors
                    print(f"  Warning: Error evaluating query '{query}': {e}")
                continue
        
        if evaluated == 0:
            print(f"  Error: No queries evaluated (skipped: {skipped})")
            p_at_10 = 0.0
        else:
            p_at_10 = float(np.mean(scores))
            if len(results) == 0:  # Only print for first result
                print(f"  Evaluated {evaluated} queries, skipped {skipped}, mean P@{top_k}: {p_at_10:.4f}")
        results.append({
            "weights": {w: getattr(weights, w) for w in active_weights},
            "p_at_10": p_at_10,
        })
        
        if p_at_10 > best_score:
            best_score = p_at_10
            best_weights = weights
    
    return {
        "best_weights": {w: getattr(best_weights, w) for w in active_weights} if best_weights else {},
        "best_score": best_score,
        "results": results,
        "active_signals": active_weights,
    }


def main():
    parser = argparse.ArgumentParser(description="Optimize fusion weights for available signals")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings file")
    parser.add_argument("--pairs", type=str, help="Path to pairs CSV (for graph data)")
    parser.add_argument("--test-set", type=str, help="Path to test set (default: unified magic)")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--output", type=str, help="Output path for optimized weights")
    parser.add_argument("--step", type=float, default=0.1, help="Grid search step size")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    
    args = parser.parse_args()
    
    # Check available signals
    print("Checking available signals...")
    signals = check_available_signals(
        Path(args.embeddings),
        Path(args.pairs) if args.pairs else None,
        Path(args.card_attrs) if args.card_attrs else None,
    )
    
    print("\nSignal availability:")
    for signal, available in signals.items():
        status = "✓" if available else "✗"
        print(f"  {status} {signal}")
    
    # Load models
    print("\nLoading models...")
    embeddings = KeyedVectors.load(args.embeddings)
    print(f"  Loaded {len(embeddings)} embeddings")
    
    adj = None
    if args.pairs and signals["graph_data"]:
        adj, _ = load_graph(args.pairs, filter_lands=True)
        print(f"  Loaded graph: {len(adj)} cards")
    
    card_attrs = None
    if args.card_attrs and signals["card_attrs"]:
        from ml.similarity.similarity_methods import load_card_attributes_csv
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
    
    # Load test set
    if args.test_set:
        test_set_path = Path(args.test_set)
    else:
        test_set_path = PATHS.test_magic
    
    print(f"\nLoading test set from {test_set_path}...")
    test_set_data = load_test_set(path=test_set_path)
    test_set = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
    print(f"  Loaded {len(test_set)} queries")
    
    # Create fusion builder
    fusion_builder = create_fusion_builder(embeddings, adj, signals, card_attrs)
    
    # Run optimization
    print("\nRunning weight optimization...")
    results = grid_search_available_signals(
        fusion_builder,
        test_set,
        signals,
        step=args.step,
        top_k=args.top_k,
    )
    
    print(f"\nBest P@10: {results['best_score']:.4f}")
    print("Best weights:")
    for signal, weight in results["best_weights"].items():
        print(f"  {signal}: {weight:.3f}")
    
    # Save results
    output_path = Path(args.output) if args.output else PATHS.experiments / "optimized_fusion_weights_latest.json"
    output_data = {
        "signals": signals,
        "active_signals": results["active_signals"],
        "best_weights": results["best_weights"],
        "best_score": results["best_score"],
        "results": results["results"],
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nSaved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

