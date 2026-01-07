#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
Enhanced learned fusion with additional features.

Adds query and candidate context features to improve learned fusion:
- Query card attributes (CMC, type, colors)
- Candidate card attributes
- Score differences between signals
- Signal agreement/disagreement
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors

from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_card_attributes_csv, load_graph
from ml.utils.data_loading import load_test_set
from ml.utils.evaluation import compute_precision_at_k
from ml.utils.paths import PATHS


def extract_enhanced_features(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    top_k: int = 10,
    sample_size: int | None = None,
) -> pd.DataFrame:
    """Extract training data with enhanced features."""
    
    # Sample test set if requested
    if sample_size and sample_size < len(test_set):
        import random
        random.seed(42)
        test_items = list(test_set.items())
        test_set = dict(random.sample(test_items, sample_size))
    
    # Create fusion instance
    weights = FusionWeights(embed=0.33, jaccard=0.33, text_embed=0.33).normalized()
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=weights,
        aggregator="weighted",
        card_data=card_attrs,
    )
    
    rows = []
    
    for query, labels in test_set.items():
        # Get all relevant cards
        if isinstance(labels, dict):
            all_relevant = set()
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
                all_relevant.update(labels.get(level, []))
        else:
            all_relevant = set(labels if isinstance(labels, list) else [])
        
        if not all_relevant:
            continue
        
        # Get query card attributes
        query_attrs = card_attrs.get(query, {}) if card_attrs else {}
        query_cmc = float(query_attrs.get("CMC", 0)) if query_attrs else 0.0
        query_type = query_attrs.get("TYPE_LINE", "") if query_attrs else ""
        
        try:
            candidates = fusion._get_candidates(query)
            if not candidates:
                continue
            
            modality_scores = fusion._compute_similarity_scores(query, candidates)
            
            for candidate, scores in modality_scores.items():
                # Relevance label
                relevance = 1.0 if candidate in all_relevant else 0.0
                
                # Get candidate attributes
                candidate_attrs = card_attrs.get(candidate, {}) if card_attrs else {}
                candidate_cmc = float(candidate_attrs.get("CMC", 0)) if candidate_attrs else 0.0
                candidate_type = candidate_attrs.get("TYPE_LINE", "") if candidate_attrs else ""
                
                # Extract signal scores
                embed_score = scores.get("embed", 0.0)
                jaccard_score = scores.get("jaccard", 0.0)
                text_embed_score = scores.get("text_embed", 0.0)
                
                # Enhanced features
                row = {
                    "query": query,
                    "candidate": candidate,
                    # Signal scores
                    "embed_score": embed_score,
                    "jaccard_score": jaccard_score,
                    "text_embed_score": text_embed_score,
                    # Score differences (signal agreement)
                    "embed_jaccard_diff": abs(embed_score - jaccard_score),
                    "embed_text_diff": abs(embed_score - text_embed_score),
                    "jaccard_text_diff": abs(jaccard_score - text_embed_score),
                    # Max/min scores (signal strength)
                    "max_score": max(embed_score, jaccard_score, text_embed_score),
                    "min_score": min(embed_score, jaccard_score, text_embed_score),
                    "score_range": max(embed_score, jaccard_score, text_embed_score) - min(embed_score, jaccard_score, text_embed_score),
                    # Query context
                    "query_cmc": query_cmc,
                    "query_is_creature": 1.0 if "Creature" in query_type else 0.0,
                    "query_is_instant": 1.0 if "Instant" in query_type else 0.0,
                    "query_is_sorcery": 1.0 if "Sorcery" in query_type else 0.0,
                    # Candidate context
                    "candidate_cmc": candidate_cmc,
                    "candidate_is_creature": 1.0 if "Creature" in candidate_type else 0.0,
                    "candidate_is_instant": 1.0 if "Instant" in candidate_type else 0.0,
                    "candidate_is_sorcery": 1.0 if "Sorcery" in candidate_type else 0.0,
                    # CMC similarity
                    "cmc_diff": abs(query_cmc - candidate_cmc),
                    "cmc_same": 1.0 if query_cmc == candidate_cmc else 0.0,
                    # Relevance
                    "relevance": relevance,
                }
                rows.append(row)
                
        except Exception as e:
            print(f"  Warning: Error processing query '{query}': {e}")
            continue
    
    return pd.DataFrame(rows)


def train_enhanced_model(df: pd.DataFrame, method: str = "lightgbm") -> tuple[Any, dict]:
    """Train enhanced model with additional features."""
    
    # Feature columns (excluding query, candidate, relevance)
    feature_cols = [col for col in df.columns if col not in ["query", "candidate", "relevance"]]
    X = df[feature_cols].values
    y = df["relevance"].values
    
    # Group by query for ranking
    groups = df.groupby("query").size().values
    
    if method == "lightgbm":
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("LightGBM not installed: pip install lightgbm")
        
        model = lgb.LGBMRanker(
            objective="lambdarank",
            n_estimators=100,
            max_depth=5,  # Deeper for more complex features
            learning_rate=0.1,
            random_state=42,
            verbose=-1,
            metric="ndcg",
        )
        
        model.fit(X, y, group=groups)
        
        # Extract feature importance
        feature_importance = model.feature_importances_
        
        # Map back to signal weights (only for signal score features)
        signal_features = ["embed_score", "jaccard_score", "text_embed_score"]
        signal_importance = {}
        for i, col in enumerate(feature_cols):
            if col in signal_features:
                signal_name = col.replace("_score", "")
                signal_importance[signal_name] = float(feature_importance[i])
        
        # Normalize signal weights
        total = sum(signal_importance.values())
        if total > 0:
            weights_dict = {k: v / total for k, v in signal_importance.items()}
        else:
            weights_dict = {k: 1.0 / len(signal_importance) for k in signal_importance}
        
        return model, weights_dict
    
    else:
        raise ValueError(f"Unknown method: {method}")


def main():
    parser = argparse.ArgumentParser(description="Enhanced learned fusion with additional features")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--sample-size", type=int, default=500, help="Sample size for training")
    parser.add_argument("--method", type=str, default="lightgbm", choices=["lightgbm"], help="Learning method")
    parser.add_argument("--aggregator", type=str, default="rrf", choices=["weighted", "rrf"], help="Aggregator")
    parser.add_argument("--output", type=str, help="Output path for results")
    
    args = parser.parse_args()
    
    # Load data
    if args.test_set:
        test_set_path = Path(args.test_set)
    else:
        test_set_path = PATHS.test_magic
    
    print(f"Loading test set from {test_set_path}...")
    test_set_data = load_test_set(path=test_set_path)
    test_set = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
    print(f"  Loaded {len(test_set)} queries")
    
    print(f"\nLoading embeddings from {args.embeddings}...")
    embeddings = KeyedVectors.load(args.embeddings)
    print(f"  Loaded {len(embeddings)} embeddings")
    
    adj, _ = load_graph(args.pairs, filter_lands=True)
    print(f"  Loaded graph: {len(adj)} cards")
    
    card_attrs = None
    if args.card_attrs:
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
    
    # Extract enhanced training data
    print(f"\nExtracting enhanced training data...")
    df = extract_enhanced_features(
        test_set, embeddings, adj, card_attrs, args.top_k, args.sample_size
    )
    print(f"  Extracted {len(df)} training examples")
    print(f"  Features: {len(df.columns) - 3} (excluding query, candidate, relevance)")
    print(f"  Positive examples: {df['relevance'].sum()} ({df['relevance'].mean()*100:.1f}%)")
    
    # Train model
    print(f"\nTraining enhanced {args.method} model...")
    model, weights = train_enhanced_model(df, args.method)
    
    print(f"  Learned weights:")
    for signal, weight in weights.items():
        print(f"    {signal}: {weight:.3f}")
    
    # Evaluate (using simple weights for now)
    from ml.similarity.fusion import FusionWeights, WeightedLateFusion
    from ml.utils.evaluation import compute_precision_at_k
    
    fusion_weights = FusionWeights(
        embed=weights.get("embed", 0.0),
        jaccard=weights.get("jaccard", 0.0),
        text_embed=weights.get("text_embed", 0.0),
    ).normalized()
    
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=fusion_weights,
        aggregator=args.aggregator,
        card_data=card_attrs,
    )
    
    print(f"\nEvaluating enhanced learned weights...")
    scores = []
    for query, labels in test_set.items():
        try:
            predictions = fusion.similar(query, args.top_k)
            if not predictions:
                continue
            
            pred_cards = [card for card, _ in predictions]
            
            if isinstance(labels, dict):
                labels_dict = labels
            else:
                labels_dict = {
                    "highly_relevant": labels if isinstance(labels, list) else [],
                    "relevant": [],
                    "somewhat_relevant": [],
                    "marginally_relevant": [],
                    "irrelevant": [],
                }
            
            p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=args.top_k)
            scores.append(p_at_k)
        except Exception:
            continue
    
    p_at_k_mean = float(np.mean(scores)) if scores else 0.0
    print(f"  P@{args.top_k}: {p_at_k_mean:.4f} ± {np.std(scores):.4f}")
    print(f"  Queries evaluated: {len(scores)}")
    
    # Save results
    if args.output:
        results = {
            "method": args.method,
            "learned_weights": weights,
            "evaluation": {
                "p_at_k": p_at_k_mean,
                "std": float(np.std(scores)) if scores else 0.0,
                "num_queries": len(scores),
            },
            "num_features": len(df.columns) - 3,
        }
        
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    from typing import Any
    sys.exit(main())

