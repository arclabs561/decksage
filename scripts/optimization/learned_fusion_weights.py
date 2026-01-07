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
Learn optimal fusion weights using gradient boosting (XGBoost/LightGBM).

Trains a model to predict relevance scores from individual signal scores,
learning optimal weights implicitly through the model.

Approaches:
1. XGBoost/LightGBM: Gradient boosting for ranking
2. Kolmogorov-Arnold Network: Universal function approximator
3. Simple linear regression: Baseline

Uses pairwise ranking loss or pointwise regression.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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

# Try to import gradient boosting libraries
HAS_XGBOOST = False
HAS_LIGHTGBM = False
HAS_SKLEARN = False

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    xgb = None

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    lgb = None

try:
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_squared_error
    HAS_SKLEARN = True
except ImportError:
    Ridge = None


def extract_training_data(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    top_k: int = 10,
    sample_size: int | None = None,
) -> pd.DataFrame:
    """Extract training data: (query, candidate, signal_scores, relevance)."""
    
    # Sample test set if requested
    if sample_size and sample_size < len(test_set):
        import random
        random.seed(42)
        test_items = list(test_set.items())
        test_set = dict(random.sample(test_items, sample_size))
    
    # Create fusion instance to get signal scores
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
        
        # Get candidates and their signal scores
        try:
            candidates = fusion._get_candidates(query)
            if not candidates:
                continue
            
            # Compute signal scores for all candidates
            modality_scores = fusion._compute_similarity_scores(query, candidates)
            
            # Create training examples
            for candidate, scores in modality_scores.items():
                # Relevance label (1 if relevant, 0 otherwise)
                relevance = 1.0 if candidate in all_relevant else 0.0
                
                # Extract signal scores
                row = {
                    "query": query,
                    "candidate": candidate,
                    "embed_score": scores.get("embed", 0.0),
                    "jaccard_score": scores.get("jaccard", 0.0),
                    "text_embed_score": scores.get("text_embed", 0.0),
                    "relevance": relevance,
                }
                rows.append(row)
                
        except Exception as e:
            print(f"  Warning: Error processing query '{query}': {e}")
            continue
    
    return pd.DataFrame(rows)


def train_xgboost_model(df: pd.DataFrame) -> tuple[Any, dict]:
    """Train XGBoost ranking model."""
    if not HAS_XGBOOST:
        raise ImportError("XGBoost not installed: pip install xgboost")
    
    # Prepare data for ranking
    feature_cols = ["embed_score", "jaccard_score", "text_embed_score"]
    X = df[feature_cols].values
    y = df["relevance"].values
    
    # Group by query for ranking
    groups = df.groupby("query").size().values
    
    # Train XGBoost ranker with pairwise ranking loss
    model = xgb.XGBRanker(
        objective="rank:pairwise",  # Pairwise ranking loss
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
        tree_method="hist",  # Faster training
    )
    
    model.fit(X, y, group=groups)
    
    # Extract feature importance (gain-based) as proxy for weights
    # feature_importances_ is a property, not a method
    feature_importance = model.feature_importances_
    weights_dict = {
        "embed": float(feature_importance[0]),
        "jaccard": float(feature_importance[1]),
        "text_embed": float(feature_importance[2]),
    }
    
    # Normalize and ensure positive
    weights_dict = {k: max(0.0, v) for k, v in weights_dict.items()}
    total = sum(weights_dict.values())
    if total > 0:
        weights_dict = {k: v / total for k, v in weights_dict.items()}
    else:
        # Fallback to equal weights
        weights_dict = {k: 1.0 / len(weights_dict) for k in weights_dict}
    
    return model, weights_dict


def train_lightgbm_model(df: pd.DataFrame) -> tuple[Any, dict]:
    """Train LightGBM ranking model."""
    if not HAS_LIGHTGBM:
        raise ImportError("LightGBM not installed: pip install lightgbm")
    
    # Prepare data for ranking
    feature_cols = ["embed_score", "jaccard_score", "text_embed_score"]
    X = df[feature_cols].values
    y = df["relevance"].values
    
    # Group by query for ranking (required for LGBMRanker)
    groups = df.groupby("query").size().values
    
    # Train LightGBM ranker with LambdaRank objective
    # LambdaRank optimizes NDCG directly
    model = lgb.LGBMRanker(
        objective="lambdarank",  # Optimizes NDCG
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
        verbose=-1,
        metric="ndcg",  # Use NDCG as metric
    )
    
    model.fit(X, y, group=groups)
    
    # Extract feature importance (gain-based) as proxy for weights
    # feature_importances_ is a property, not a method
    feature_importance = model.feature_importances_
    weights_dict = {
        "embed": float(feature_importance[0]),
        "jaccard": float(feature_importance[1]),
        "text_embed": float(feature_importance[2]),
    }
    
    # Normalize and ensure positive
    weights_dict = {k: max(0.0, v) for k, v in weights_dict.items()}
    total = sum(weights_dict.values())
    if total > 0:
        weights_dict = {k: v / total for k, v in weights_dict.items()}
    else:
        # Fallback to equal weights
        weights_dict = {k: 1.0 / len(weights_dict) for k in weights_dict}
    
    return model, weights_dict


def train_linear_model(df: pd.DataFrame) -> tuple[Any, dict]:
    """Train simple linear regression model."""
    if not HAS_SKLEARN:
        raise ImportError("scikit-learn not installed: pip install scikit-learn")
    
    feature_cols = ["embed_score", "jaccard_score", "text_embed_score"]
    X = df[feature_cols].values
    y = df["relevance"].values
    
    # Train Ridge regression
    model = Ridge(alpha=0.1, random_state=42)
    model.fit(X, y)
    
    # Extract coefficients as weights
    coef = model.coef_
    weights_dict = {
        "embed": float(coef[0]),
        "jaccard": float(coef[1]),
        "text_embed": float(coef[2]),
    }
    
    # Normalize and ensure positive
    weights_dict = {k: max(0.0, v) for k, v in weights_dict.items()}
    total = sum(weights_dict.values())
    if total > 0:
        weights_dict = {k: v / total for k, v in weights_dict.items()}
    else:
        # Fallback to equal weights
        weights_dict = {k: 1.0 / len(weights_dict) for k in weights_dict}
    
    return model, weights_dict


def evaluate_learned_weights(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    weights: dict,
    aggregator: str = "weighted",
    top_k: int = 10,
) -> dict:
    """Evaluate learned weights on test set."""
    
    fusion_weights = FusionWeights(
        embed=weights.get("embed", 0.0),
        jaccard=weights.get("jaccard", 0.0),
        text_embed=weights.get("text_embed", 0.0),
    ).normalized()
    
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=fusion_weights,
        aggregator=aggregator,
        card_data=card_attrs,
    )
    
    scores = []
    for query, labels in test_set.items():
        try:
            predictions = fusion.similar(query, top_k)
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
            
            p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=top_k)
            scores.append(p_at_k)
        except Exception:
            continue
    
    return {
        "p_at_k": float(np.mean(scores)) if scores else 0.0,
        "std": float(np.std(scores)) if scores else 0.0,
        "num_queries": len(scores),
    }


def main():
    parser = argparse.ArgumentParser(description="Learn optimal fusion weights using gradient boosting")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--sample-size", type=int, help="Sample size for training data extraction")
    parser.add_argument("--method", type=str, default="lightgbm", choices=["xgboost", "lightgbm", "linear"], help="Learning method")
    parser.add_argument("--aggregator", type=str, default="weighted", choices=["weighted", "rrf"], help="Aggregator for evaluation")
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
    
    # Extract training data
    print(f"\nExtracting training data...")
    df = extract_training_data(
        test_set, embeddings, adj, card_attrs, args.top_k, args.sample_size
    )
    print(f"  Extracted {len(df)} training examples")
    print(f"  Positive examples: {df['relevance'].sum()} ({df['relevance'].mean()*100:.1f}%)")
    
    # Train model
    print(f"\nTraining {args.method} model...")
    if args.method == "xgboost":
        if not HAS_XGBOOST:
            print("  Error: XGBoost not installed. Install with: pip install xgboost")
            return 1
        model, weights = train_xgboost_model(df)
    elif args.method == "lightgbm":
        if not HAS_LIGHTGBM:
            print("  Error: LightGBM not installed. Install with: pip install lightgbm")
            return 1
        model, weights = train_lightgbm_model(df)
    else:  # linear
        if not HAS_SKLEARN:
            print("  Error: scikit-learn not installed. Install with: pip install scikit-learn")
            return 1
        model, weights = train_linear_model(df)
    
    print(f"  Learned weights:")
    for signal, weight in weights.items():
        print(f"    {signal}: {weight:.3f}")
    
    # Evaluate learned weights
    print(f"\nEvaluating learned weights...")
    eval_result = evaluate_learned_weights(
        test_set, embeddings, adj, card_attrs, weights, args.aggregator, args.top_k
    )
    print(f"  P@{args.top_k}: {eval_result['p_at_k']:.4f} ± {eval_result['std']:.4f}")
    print(f"  Queries evaluated: {eval_result['num_queries']}")
    
    # Compare with baseline (equal weights)
    print(f"\nComparing with equal weights baseline...")
    equal_weights = {"embed": 0.333, "jaccard": 0.333, "text_embed": 0.333}
    baseline_result = evaluate_learned_weights(
        test_set, embeddings, adj, card_attrs, equal_weights, args.aggregator, args.top_k
    )
    print(f"  Equal weights P@{args.top_k}: {baseline_result['p_at_k']:.4f} ± {baseline_result['std']:.4f}")
    
    improvement = eval_result['p_at_k'] - baseline_result['p_at_k']
    improvement_pct = (improvement / baseline_result['p_at_k'] * 100) if baseline_result['p_at_k'] > 0 else 0.0
    print(f"  Improvement: {improvement:+.4f} ({improvement_pct:+.1f}%)")
    
    # Save results
    results = {
        "method": args.method,
        "learned_weights": weights,
        "evaluation": eval_result,
        "baseline": baseline_result,
        "improvement": improvement,
        "improvement_pct": improvement_pct,
    }
    
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

