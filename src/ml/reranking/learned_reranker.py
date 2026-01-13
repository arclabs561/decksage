#!/usr/bin/env python3
"""
Learned Reranker for Learning-to-Rank.

Uses gradient boosting models (LightGBM/XGBoost) to learn optimal
combination of similarity features from labeled data.
"""

from __future__ import annotations

import logging
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)

# Try to import gradient boosting libraries
HAS_LIGHTGBM = False
HAS_XGBOOST = False

try:
    import lightgbm as lgb

    HAS_LIGHTGBM = True
except ImportError:
    lgb = None

try:
    import xgboost as xgb

    HAS_XGBOOST = True
except ImportError:
    xgb = None


class LearnedReranker:
    """
    Learned reranker using gradient boosting (LightGBM/XGBoost).

    Trains a model to predict relevance scores from feature vectors,
    learning optimal feature combination from labeled data.
    """

    def __init__(self, model_path: str | Path | None = None):
        """
        Initialize reranker.

        Args:
            model_path: Path to saved model (optional)
        """
        self.model: Any = None
        self.feature_names: list[str] | None = None

        if model_path:
            self.load(model_path)

    def rerank(
        self,
        query: str,
        candidates: list[str],
        feature_extractor: Callable[[str, str], dict[str, float]],
    ) -> list[tuple[str, float]]:
        """
        Rerank candidates using learned model.

        Args:
            query: Query card name
            candidates: List of candidate card names
            feature_extractor: Function that extracts features for (query, candidate) pair

        Returns:
            List of (candidate, score) tuples, sorted by score descending
        """
        if self.model is None:
            raise ValueError("Model not loaded. Train or load a model first.")

        if not candidates:
            return []

        # Extract features for all query-candidate pairs (parallelize if possible)
        try:
            from concurrent.futures import ThreadPoolExecutor

            # Use thread pool for I/O-bound feature extraction
            with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as executor:
                features_list = list(
                    executor.map(lambda c: feature_extractor(query, c), candidates)
                )
        except ImportError:
            # Fallback to sequential if concurrent.futures not available
            features_list = [feature_extractor(query, candidate) for candidate in candidates]

        # Convert to DataFrame
        df = pd.DataFrame(features_list)

        # Ensure feature order matches training (if feature_names available)
        if self.feature_names:
            # Add missing features as 0.0
            for col in self.feature_names:
                if col not in df.columns:
                    df[col] = 0.0
            # Select only training features in correct order
            df = df[self.feature_names]
        else:
            # If no feature names stored, infer from first feature dict
            if features_list:
                self.feature_names = list(features_list[0].keys())
                df = df[self.feature_names]

        # Predict relevance scores (use DataFrame directly to preserve feature names)
        try:
            scores = self.model.predict(df)
        except Exception as e:
            logger.error(f"Error predicting scores: {e}")
            # Fallback: return candidates with zero scores
            return [(c, 0.0) for c in candidates]

        # Sort by predicted score
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return ranked

    def train(
        self,
        training_data: pd.DataFrame,
        method: str = "lightgbm",
        feature_cols: list[str] | None = None,
        **kwargs,
    ) -> None:
        """
        Train reranker on labeled data.

        Args:
            training_data: DataFrame with columns: query, candidate, relevance, and feature columns
            method: "lightgbm" or "xgboost"
            feature_cols: List of feature column names (auto-detected if None)
            **kwargs: Additional model parameters
        """
        # Prepare features and labels
        if feature_cols is None:
            feature_cols = [
                col
                for col in training_data.columns
                if col not in ["query", "candidate", "relevance"]
            ]

        X = training_data[feature_cols]  # Keep as DataFrame to preserve feature names
        y = training_data["relevance"].values

        # Group by query (required for ranking models)
        groups = training_data.groupby("query").size().values

        # Store feature names for inference
        self.feature_names = feature_cols

        # Train model
        if method == "lightgbm":
            if not HAS_LIGHTGBM:
                raise ImportError("LightGBM not installed: pip install lightgbm")

            self.model = lgb.LGBMRanker(
                objective="lambdarank",  # Optimizes NDCG directly
                n_estimators=kwargs.get("n_estimators", 200),
                max_depth=kwargs.get("max_depth", 6),
                learning_rate=kwargs.get("learning_rate", 0.05),
                metric="ndcg@10",
                random_state=kwargs.get("random_state", 42),
                verbose=kwargs.get("verbose", -1),
            )

            self.model.fit(X, y, group=groups)

        elif method == "xgboost":
            if not HAS_XGBOOST:
                raise ImportError("XGBoost not installed: pip install xgboost")

            self.model = xgb.XGBRanker(
                objective="rank:pairwise",
                n_estimators=kwargs.get("n_estimators", 200),
                max_depth=kwargs.get("max_depth", 6),
                learning_rate=kwargs.get("learning_rate", 0.05),
                random_state=kwargs.get("random_state", 42),
                tree_method=kwargs.get("tree_method", "hist"),
            )

            # XGBoost also accepts DataFrame directly
            self.model.fit(X, y, group=groups)

        else:
            raise ValueError(f"Unknown method: {method}. Use 'lightgbm' or 'xgboost'")

        logger.info(f"Trained {method} reranker with {len(feature_cols)} features")

    def save(self, path: str | Path) -> None:
        """
        Save trained model.

        Args:
            path: Path to save model
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "feature_names": self.feature_names,
        }

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        logger.info(f"Saved reranker to {path}")

    def load(self, path: str | Path) -> None:
        """
        Load trained model.

        Args:
            path: Path to saved model
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        with open(path, "rb") as f:
            model_data = pickle.load(f)

        self.model = model_data["model"]
        self.feature_names = model_data.get("feature_names")

        logger.info(f"Loaded reranker from {path}")

    def get_feature_importance(self) -> dict[str, float] | None:
        """
        Get feature importance from trained model.

        Returns:
            Dictionary mapping feature names to importance scores, or None if model not trained
        """
        if self.model is None or self.feature_names is None:
            return None

        try:
            importances = self.model.feature_importances_
            return dict(zip(self.feature_names, importances))
        except AttributeError:
            logger.warning("Model does not support feature_importances_")
            return None


__all__ = ["HAS_LIGHTGBM", "HAS_XGBOOST", "LearnedReranker"]
