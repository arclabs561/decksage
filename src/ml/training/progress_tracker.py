"""Progress tracking and intermediate checkpointing for training pipelines.

Saves intermediate progress at regular intervals:
- Training metrics (loss, validation scores)
- Model checkpoints
- Embedding snapshots
- Training statistics
- Progress logs

Designed for long-running training jobs where intermediate progress
is critical for monitoring and recovery.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ..utils.logging_config import get_logger, log_progress, log_checkpoint, get_correlation_id
    logger = get_logger(__name__)
    HAS_LOGGING_CONFIG = True
except ImportError:
            logger = logging.getLogger(__name__)
            HAS_LOGGING_CONFIG = False
            # Fallback functions
            def log_progress(logger, stage, progress=None, total=None, **kwargs):
                if isinstance(progress, (int, float)) and total:
                    logger.info(f"{stage}: {progress}/{total}")
                else:
                    logger.info(f"{stage}: {progress}")
            def log_checkpoint(logger, name, checkpoint_path=None, **kwargs):
                logger.info(f"Checkpoint {name} saved" + (f" to {checkpoint_path}" if checkpoint_path else ""))
            def get_correlation_id():
                return None


class TrainingProgressTracker:
    """Track and save intermediate training progress."""
    
    def __init__(
        self,
        output_dir: Path,
        checkpoint_interval: int = 10,
        metrics_interval: int = 1,
        save_intermediate_embeddings: bool = False,
    ):
        """
        Initialize progress tracker.
        
        Args:
            output_dir: Directory to save progress files
            checkpoint_interval: Save checkpoint every N epochs
            metrics_interval: Save metrics every N epochs
            save_intermediate_embeddings: Save embedding snapshots (memory intensive)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.checkpoint_interval = checkpoint_interval
        self.metrics_interval = metrics_interval
        self.save_intermediate_embeddings = save_intermediate_embeddings
        
        # Progress tracking
        self.metrics_history: list[dict[str, Any]] = []
        self.checkpoints: list[dict[str, Any]] = []
        self.start_time = datetime.now()
        
        # Progress file paths
        self.metrics_file = self.output_dir / "training_metrics.jsonl"
        self.progress_file = self.output_dir / "training_progress.json"
        self.checkpoints_dir = self.output_dir / "checkpoints"
        self.checkpoints_dir.mkdir(exist_ok=True)
        
        logger.info(f"Progress tracker initialized: {self.output_dir}")
        logger.info(f"  Checkpoint interval: {checkpoint_interval} epochs")
        logger.info(f"  Metrics interval: {metrics_interval} epochs")
    
    def log_metrics(
        self,
        epoch: int,
        metrics: dict[str, float],
        embeddings_path: Path | None = None,
    ) -> None:
        """
        Log training metrics for an epoch.
        
        Args:
            epoch: Current epoch number
            metrics: Dictionary of metric names to values
            embeddings_path: Optional path to embeddings file
        """
        metric_entry = {
            "epoch": epoch,
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds(),
            "metrics": metrics,
        }
        
        # Add correlation ID if available
        if HAS_LOGGING_CONFIG:
            corr_id = get_correlation_id()
            if corr_id:
                metric_entry["correlation_id"] = corr_id
        
        if embeddings_path:
            metric_entry["embeddings_path"] = str(embeddings_path)
        
        # Append to JSONL file (append-only, efficient)
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(metric_entry) + "\n")
        
        self.metrics_history.append(metric_entry)
        
        # Update progress summary
        self._update_progress_summary(epoch, metrics)
        
        if epoch % self.metrics_interval == 0:
            try:
                log_progress(logger, "metrics", progress=epoch, metrics=metrics)
            except NameError:
                logger.info(f"Metrics logged (epoch {epoch}): {metrics}")
    
    def save_checkpoint(
        self,
        epoch: int,
        checkpoint_data: dict[str, Any],
        checkpoint_path: Path | None = None,
    ) -> Path:
        """
        Save a training checkpoint.
        
        Args:
            epoch: Current epoch number
            checkpoint_data: Dictionary containing checkpoint data
            checkpoint_path: Optional custom path, otherwise auto-generated
            
        Returns:
            Path to saved checkpoint
        """
        if checkpoint_path is None:
            checkpoint_path = self.checkpoints_dir / f"checkpoint_epoch_{epoch:04d}.json"
        
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        checkpoint = {
            "epoch": epoch,
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds(),
            **checkpoint_data,
        }
        
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)
        
        self.checkpoints.append({
            "epoch": epoch,
            "path": str(checkpoint_path),
            "timestamp": checkpoint["timestamp"],
        })
        
        try:
            checkpoint_name = f"epoch_{epoch}"
            log_checkpoint(logger, checkpoint_name, checkpoint_path=checkpoint_path, epoch=epoch)
        except NameError:
            logger.info(f"Checkpoint saved: {checkpoint_path}")
        return checkpoint_path
    
    def save_intermediate_embeddings(
        self,
        epoch: int,
        embeddings: dict[str, Any],
    ) -> Path:
        """
        Save intermediate embeddings snapshot.
        
        Args:
            epoch: Current epoch number
            embeddings: Embeddings dictionary (card -> vector)
            
        Returns:
            Path to saved embeddings
        """
        if not self.save_intermediate_embeddings:
            return Path()
        
        embeddings_path = self.output_dir / "intermediate_embeddings" / f"embeddings_epoch_{epoch:04d}.json"
        embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON (can be large, but allows inspection)
        with open(embeddings_path, "w") as f:
            json.dump({
                "epoch": epoch,
                "timestamp": datetime.now().isoformat(),
                "num_cards": len(embeddings),
                "embeddings": embeddings,
            }, f, indent=2)
        
        logger.info(f"Intermediate embeddings saved: {embeddings_path} ({len(embeddings)} cards)")
        return embeddings_path
    
    def _update_progress_summary(self, epoch: int, metrics: dict[str, float]) -> None:
        """Update progress summary file."""
        progress = {
            "last_epoch": epoch,
            "last_update": datetime.now().isoformat(),
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds(),
            "total_metrics": len(self.metrics_history),
            "total_checkpoints": len(self.checkpoints),
            "latest_metrics": metrics,
            "best_metrics": self._get_best_metrics(),
        }
        
        # Add correlation ID if available
        if HAS_LOGGING_CONFIG:
            corr_id = get_correlation_id()
            if corr_id:
                progress["correlation_id"] = corr_id
        
        with open(self.progress_file, "w") as f:
            json.dump(progress, f, indent=2)
    
    def _get_best_metrics(self) -> dict[str, float]:
        """Extract best metrics from history."""
        if not self.metrics_history:
            return {}
        
        best = {}
        for entry in self.metrics_history:
            for metric_name, value in entry["metrics"].items():
                if metric_name not in best:
                    best[metric_name] = value
                else:
                    # For loss metrics, lower is better; for scores, higher is better
                    if "loss" in metric_name.lower():
                        best[metric_name] = min(best[metric_name], value)
                    else:
                        best[metric_name] = max(best[metric_name], value)
        
        return best
    
    def get_latest_progress(self) -> dict[str, Any]:
        """Get latest progress summary."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {}
    
    def get_metrics_history(self, last_n: int | None = None) -> list[dict[str, Any]]:
        """Get metrics history, optionally limited to last N entries."""
        if last_n is None:
            return self.metrics_history
        return self.metrics_history[-last_n:]


def save_training_stats(
    output_dir: Path,
    stats: dict[str, Any],
) -> Path:
    """
    Save training statistics (one-time, at start or end).
    
    Args:
        output_dir: Directory to save stats
        stats: Statistics dictionary
        
    Returns:
        Path to saved stats file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    stats_file = output_dir / "training_stats.json"
    
    stats["timestamp"] = datetime.now().isoformat()
    
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Training stats saved: {stats_file}")
    return stats_file

