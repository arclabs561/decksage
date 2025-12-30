"""AimStack integration helpers for consistent experiment tracking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import aim
    HAS_AIM = True
except ImportError:
    HAS_AIM = False
    aim = None

logger = logging.getLogger(__name__)

# Default Aim repository location
AIM_REPO = Path(".aim")


def create_training_run(
    experiment_name: str,
    hparams: dict[str, Any],
    tags: list[str] | None = None,
    repo: Path | str | None = None,
) -> aim.Run | None:
    """Create an Aim run for training experiments."""
    if not HAS_AIM:
        logger.warning("AimStack not available, skipping tracking")
        return None
    
    try:
        run = aim.Run(
            experiment=experiment_name,
            repo=str(repo or AIM_REPO),
            hparams=hparams,
            tags=tags or [],
        )
        logger.info(f"Created Aim run: {experiment_name}")
        return run
    except Exception as e:
        logger.error(f"Failed to create Aim run: {e}")
        return None


def track_training_metrics(
    run: aim.Run | None,
    epoch: int,
    train_loss: float | None = None,
    val_loss: float | None = None,
    val_p10: float | None = None,
    learning_rate: float | None = None,
    test_p10: float | None = None,
) -> None:
    """Track standard training metrics."""
    if run is None:
        return
    
    try:
        if train_loss is not None:
            run.track(train_loss, name="loss", context={"subset": "train"}, step=epoch)
        if val_loss is not None:
            run.track(val_loss, name="loss", context={"subset": "val"}, step=epoch)
        if val_p10 is not None:
            run.track(val_p10, name="p10", context={"subset": "val"}, step=epoch)
        if test_p10 is not None:
            run.track(test_p10, name="p10", context={"subset": "test"}, step=epoch)
        if learning_rate is not None:
            run.track(learning_rate, name="learning_rate", step=epoch)
    except Exception as e:
        logger.error(f"Failed to track training metrics: {e}")


def track_evaluation_metrics(
    run: aim.Run | None,
    p10: float,
    ndcg: float | None = None,
    mrr: float | None = None,
    method: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Track evaluation metrics."""
    if run is None:
        return
    
    try:
        ctx = context or {}
        if method:
            ctx["method"] = method
        
        run.track(p10, name="p10", context=ctx)
        if ndcg is not None:
            run.track(ndcg, name="ndcg", context=ctx)
        if mrr is not None:
            run.track(mrr, name="mrr", context=ctx)
    except Exception as e:
        logger.error(f"Failed to track evaluation metrics: {e}")


def track_hyperparameter_result(
    run: aim.Run | None,
    params: dict[str, Any],
    results: dict[str, float],
) -> None:
    """Track hyperparameter search results."""
    if run is None:
        return
    
    try:
        # Track all hyperparameters
        for key, value in params.items():
            run.track(value, name="hyperparameter", context={"param": key})
        
        # Track all results
        for metric, value in results.items():
            run.track(value, name=metric, context={"config": str(params)})
    except Exception as e:
        logger.error(f"Failed to track hyperparameter result: {e}")


def track_artifact(
    run: aim.Run | None,
    artifact_path: str | Path,
    name: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Track an artifact (file) in Aim."""
    if run is None:
        return
    
    try:
        run.track(str(artifact_path), name=name, context=context or {})
    except Exception as e:
        logger.error(f"Failed to track artifact: {e}")

