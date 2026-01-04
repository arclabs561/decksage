"""
Training Registry Integration

Helper utilities to register training runs and models in the evaluation registry.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .evaluation_registry import EvaluationRegistry
from .path_resolution import version_path

try:
    from .logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def register_training_run(
    model_type: str,
    model_path: Path | str,
    output_path: Path | str,
    training_metadata: dict[str, Any] | None = None,
    version: str | None = None,
) -> str:
    """
    Register a training run in the model registry.
    
    Args:
        model_type: Type of model (e.g., "cooccurrence", "gnn", "hybrid")
        model_path: Path to trained model file
        output_path: Path where model was saved
        training_metadata: Training parameters and metadata
        version: Version tag (if None, auto-generates from timestamp)
    
    Returns:
        Version string used for registration
    """
    if version is None:
        # Auto-generate version: YYYY-WWW format (week number)
        version = datetime.now().strftime("%Y-W%V")
    
    registry = EvaluationRegistry()
    
    # Register model (without evaluation metrics yet)
    registry.model_registry.register_model(
        model_type=model_type,
        version=version,
        path=model_path,
        metrics=None,  # Will be filled when evaluation is recorded
        metadata={
            **(training_metadata or {}),
            "training_timestamp": datetime.now().isoformat(),
            "output_path": str(output_path),
        },
        is_production=False,  # Not production until explicitly promoted
    )
    
    logger.info(f"Registered training run: {model_type} v{version}")
    return version


def register_training_with_evaluation(
    model_type: str,
    model_path: Path | str,
    evaluation_results: dict[str, Any],
    test_set_path: Path | str | None = None,
    training_metadata: dict[str, Any] | None = None,
    version: str | None = None,
    is_production: bool = False,
) -> str:
    """
    Register a training run with evaluation results.
    
    Convenience function that combines training registration and evaluation recording.
    
    Args:
        model_type: Type of model
        model_path: Path to trained model
        evaluation_results: Evaluation results dict
        test_set_path: Path to test set used
        training_metadata: Training parameters
        version: Version tag (auto-generated if None)
        is_production: Whether this is a production model
    
    Returns:
        Version string used
    """
    if version is None:
        version = datetime.now().strftime("%Y-W%V")
    
    registry = EvaluationRegistry()
    
    # Record evaluation (this also registers the model)
    results_file = registry.record_evaluation(
        model_type=model_type,
        model_version=version,
        model_path=model_path,
        evaluation_results=evaluation_results,
        test_set_path=test_set_path,
        metadata=training_metadata,
        is_production=is_production,
    )
    
    logger.info(f"Registered training + evaluation: {model_type} v{version}")
    logger.info(f"  Results file: {results_file}")
    
    return version

