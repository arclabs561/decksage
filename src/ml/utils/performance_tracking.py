"""Performance tracking utilities for training and evaluation scripts.

This module is small on purpose: it provides timing + structured metadata that
can be written to a JSON file for later inspection.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger(__name__)


@dataclass
class StageRecord:
    elapsed_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


class PerformanceTracker:
    """Track wall-clock timings and lightweight metrics."""

    def __init__(self, output_path: Path | str | None = None):
        self.output_path = Path(output_path) if output_path else None
        self.started_at = datetime.now()
        self._stage_started_at: dict[str, float] = {}
        self._stage_counts: dict[str, int] = defaultdict(int)

        self.metrics: dict[str, Any] = {
            "start_time": self.started_at.isoformat(),
            "end_time": None,
            "success": None,
            "error": None,
            "total_time_seconds": None,
            "stages": {},
            "custom_metrics": {},
            "memory_usage_mb": {},
        }

    def start_stage(self, stage_name: str) -> None:
        """Start timing a stage."""
        self._stage_started_at[stage_name] = time.time()
        self._stage_counts[stage_name] += 1
        logger.info("Starting stage: %s", stage_name)

    def end_stage(self, stage_name: str, metadata: dict[str, Any] | None = None) -> float:
        """Stop timing a stage and record its elapsed time."""
        if stage_name not in self._stage_started_at:
            logger.warning("Stage %s was not started", stage_name)
            return 0.0

        elapsed = time.time() - self._stage_started_at[stage_name]
        idx = self._stage_counts[stage_name]
        stage_key = f"{stage_name}_{idx}"
        self.metrics["stages"][stage_key] = {
            "elapsed_seconds": elapsed,
            "metadata": metadata or {},
        }
        logger.info("Completed stage: %s (%.2fs)", stage_name, elapsed)
        self._stage_started_at.pop(stage_name, None)
        return float(elapsed)

    def record_metric(self, name: str, value: Any, *, unit: str | None = None) -> None:
        """Record a custom metric."""
        key = f"{name}_{unit}" if unit else name
        self.metrics["custom_metrics"][key] = value

    def record_memory(self, stage: str, memory_mb: float) -> None:
        """Record memory usage for a stage (best-effort)."""
        self.metrics["memory_usage_mb"][stage] = float(memory_mb)

    def finish(self, *, success: bool = True, error: str | None = None) -> dict[str, Any]:
        """Finalize metrics and optionally write them to disk."""
        ended_at = datetime.now()
        total_seconds = (ended_at - self.started_at).total_seconds()

        self.metrics["end_time"] = ended_at.isoformat()
        self.metrics["success"] = bool(success)
        self.metrics["error"] = error
        self.metrics["total_time_seconds"] = float(total_seconds)

        if self.output_path:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(json.dumps(self.metrics, indent=2, sort_keys=True) + "\n")
            logger.info("Wrote performance metrics to %s", self.output_path)

        return self.metrics

    def get_summary(self) -> str:
        """Return a small human-readable summary (no tables)."""
        total = self.metrics.get("total_time_seconds")
        if total is None:
            return "No metrics recorded yet"
        num_stages = len(self.metrics.get("stages", {}))
        return f"total_time_seconds={total:.2f}, stages={num_stages}"
