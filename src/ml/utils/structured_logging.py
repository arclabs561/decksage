"""Structured logging utilities for automation scripts."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .logging_config import get_logger

logger = get_logger(__name__)


class StructuredLogger:
    """Logger that writes structured JSON logs alongside human-readable logs."""
    
    def __init__(
        self,
        json_log_path: Path | str,
        human_log_path: Path | str | None = None,
        level: int = logging.INFO,
    ):
        """
        Initialize structured logger.
        
        Args:
            json_log_path: Path to JSON log file
            human_log_path: Path to human-readable log file (optional)
            level: Logging level
        """
        self.json_log_path = Path(json_log_path)
        self.json_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.human_log_path = Path(human_log_path) if human_log_path else None
        if self.human_log_path:
            self.human_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup standard logger for human-readable output
        # Use centralized logging config if available
        try:
            from .logging_config import configure_logging
            configure_logging(level=level, force=False)
        except ImportError:
            pass
        
        self.logger = get_logger(f"{__name__}.{self.json_log_path.stem}")
        self.logger.setLevel(level)
        
        # Add file handler if specified (in addition to any existing handlers)
        if self.human_log_path:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.human_log_path,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
            )
            file_handler.setLevel(level)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(console_formatter)
            self.logger.addHandler(file_handler)
    
    def log_event(
        self,
        event_type: str,
        message: str,
        level: str = "info",
        **metadata: Any,
    ) -> None:
        """
        Log a structured event.
        
        Args:
            event_type: Type of event (e.g., "training_started", "validation_passed")
            message: Human-readable message
            level: Log level (debug, info, warning, error)
            **metadata: Additional metadata to include
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "level": level,
            "message": message,
            **metadata,
        }
        
        # Write to JSON log
        with open(self.json_log_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        # Write to human-readable log
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)
    
    def log_step(
        self,
        step_name: str,
        status: Literal["started", "completed", "failed", "skipped"],
        duration_sec: float | None = None,
        **metadata: Any,
    ) -> None:
        """
        Log a workflow step.
        
        Args:
            step_name: Name of the step
            status: Step status
            duration_sec: Duration in seconds (if completed)
            **metadata: Additional metadata
        """
        level_map = {
            "started": "info",
            "completed": "info",
            "failed": "error",
            "skipped": "warning",
        }
        
        message = f"Step '{step_name}': {status}"
        if duration_sec is not None:
            message += f" (took {duration_sec:.2f}s)"
        
        self.log_event(
            event_type=f"step_{status}",
            message=message,
            level=level_map.get(status, "info"),
            step_name=step_name,
            status=status,
            duration_sec=duration_sec,
            **metadata,
        )
    
    def log_validation(
        self,
        validation_name: str,
        passed: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        **metadata: Any,
    ) -> None:
        """
        Log validation results.
        
        Args:
            validation_name: Name of validation
            passed: Whether validation passed
            errors: List of errors (if any)
            warnings: List of warnings (if any)
            **metadata: Additional metadata
        """
        level = "info" if passed else "error"
        message = f"Validation '{validation_name}': {'PASSED' if passed else 'FAILED'}"
        
        if errors:
            message += f" ({len(errors)} errors)"
        if warnings:
            message += f" ({len(warnings)} warnings)"
        
        self.log_event(
            event_type="validation_result",
            message=message,
            level=level,
            validation_name=validation_name,
            passed=passed,
            errors=errors or [],
            warnings=warnings or [],
            **metadata,
        )
    
    def log_metrics(
        self,
        metrics: dict[str, float],
        context: str = "training",
        **metadata: Any,
    ) -> None:
        """
        Log metrics.
        
        Args:
            metrics: Dictionary of metric name -> value
            context: Context for metrics (training, evaluation, etc.)
            **metadata: Additional metadata
        """
        message = f"Metrics ({context}): " + ", ".join(
            f"{k}={v:.4f}" for k, v in metrics.items()
        )
        
        self.log_event(
            event_type="metrics",
            message=message,
            level="info",
            context=context,
            metrics=metrics,
            **metadata,
        )


def load_json_logs(log_path: Path | str) -> list[dict[str, Any]]:
    """Load and parse JSON log file."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    
    logs = []
    with open(log_path) as f:
        for line in f:
            if line.strip():
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    return logs


def filter_logs_by_type(logs: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    """Filter logs by event type."""
    return [log for log in logs if log.get("event_type") == event_type]


def get_latest_metrics(logs: list[dict[str, Any]], context: str = "training") -> dict[str, float] | None:
    """Get latest metrics from logs."""
    metric_logs = [
        log for log in logs
        if log.get("event_type") == "metrics" and log.get("context") == context
    ]
    
    if not metric_logs:
        return None
    
    # Get most recent
    latest = sorted(metric_logs, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
    return latest.get("metrics")

