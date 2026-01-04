"""Centralized logging configuration for the DeckSage project.

This module provides a consistent logging setup across all scripts and modules.
It supports:
- Environment variable configuration (LOG_LEVEL, LOG_FORMAT)
- Structured logging with context (module, function, line number)
- Log rotation for file handlers (10MB max, 5 backups)
- Consistent formatting across all components
- Correlation IDs for tracking runs across systems (EC2, S3, monitoring)
- Progress indicators for long-running processes ([PROGRESS], [CHECKPOINT], [STAGE], [METRIC])
- Enhanced exception logging with context and correlation IDs
- Experiment name tracking for multi-experiment runs
- Hostname and process ID for distributed training

Usage:
    # For scripts:
    from ml.utils.logging_config import setup_script_logging, log_progress, log_checkpoint, log_exception
    logger = setup_script_logging(experiment_name="hybrid_v2")

    # For modules:
    from ml.utils.logging_config import get_logger
    logger = get_logger(__name__)

    # Progress tracking:
    log_progress(logger, "epoch", progress=5, total=10, loss=0.45)

    # Checkpoint logging:
    log_checkpoint(logger, "epoch_10", checkpoint_path=Path("checkpoint.wv"))

    # Exception logging:
    log_exception(logger, "Training failed", e, include_context=True)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal


# Context variables for correlation IDs and experiment names
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_experiment_name: ContextVar[str | None] = ContextVar("experiment_name", default=None)
_dataset_version: ContextVar[str | None] = ContextVar("dataset_version", default=None)
_model_architecture: ContextVar[str | None] = ContextVar("model_architecture", default=None)
_git_commit: ContextVar[str | None] = ContextVar("git_commit", default=None)
_hostname: str | None = None
# Thread-safe storage for training start times
_training_start_times: dict[str, float] = {}
_training_start_times_lock = threading.Lock()

_logging_configured = False


def get_log_level(env_var: str = "LOG_LEVEL", default: str = "INFO") -> int:
    """Get log level from environment variable or default.

    Args:
        env_var: Environment variable name
        default: Default level if not set

    Returns:
        Logging level constant
    """
    level_str = os.getenv(env_var, default).upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str, logging.INFO)


def get_log_format(env_var: str = "LOG_FORMAT", default: str = "detailed") -> str:
    """Get log format from environment variable or default.

    Args:
        env_var: Environment variable name
        default: Default format if not set

    Returns:
        Format string for logging.Formatter
    """
    format_name = os.getenv(env_var, default).lower()
    formats = {
        "standard": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "detailed": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        "minimal": "%(levelname)s - %(message)s",
    }
    return formats.get(format_name, formats["standard"])


class CorrelationIDFilter(logging.Filter):
    """Filter to add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record if available."""
        corr_id = _correlation_id.get()
        if corr_id:
            record.correlation_id = corr_id
        else:
            record.correlation_id = None
        return True


class ProgressFormatter(logging.Formatter):
    """Formatter that adds progress indicators for monitoring scripts.

    Adds parseable prefixes for common training events:
    - [PROGRESS] for progress updates
    - [CHECKPOINT] for checkpoint saves
    - [METRIC] for metric logging
    - [STAGE] for stage transitions
    """

    PROGRESS_KEYWORDS = {
        "epoch": "[PROGRESS]",
        "checkpoint": "[CHECKPOINT]",
        "saved": "[CHECKPOINT]",
        "complete": "[PROGRESS]",
        "stage": "[STAGE]",
        "metric": "[METRIC]",
        "training": "[PROGRESS]",
        "evaluation": "[PROGRESS]",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with progress indicators."""
        # Get the final message
        message = record.getMessage()

        # Skip if message already starts with a known prefix (avoid duplicates)
        # Also check if prefix appears early in message (after correlation ID)
        known_prefixes = ["[PROGRESS]", "[CHECKPOINT]", "[STAGE]", "[METRIC]"]
        if any(message.startswith(prefix) for prefix in known_prefixes):
            return super().format(record)
        # Check if prefix appears after correlation ID pattern [hex8]
        if any(f"[{prefix[1:-1]}]" in message[:50] for prefix in known_prefixes):
            return super().format(record)

        # Check if message contains progress keywords (only if no prefix exists)
        message_lower = message.lower()
        prefix = ""
        for keyword, indicator in self.PROGRESS_KEYWORDS.items():
            if keyword in message_lower:
                prefix = indicator
                break

        # Add prefix if found
        if prefix:
            original_msg = record.msg
            record.msg = f"{prefix} {original_msg}"

        return super().format(record)


def _get_hostname() -> str:
    """Get hostname for logging context."""
    global _hostname
    if _hostname is None:
        import socket

        try:
            _hostname = socket.gethostname()
        except Exception:
            _hostname = "unknown"
    return _hostname


def set_correlation_id(corr_id: str | None = None) -> str:
    """Set correlation ID for current context.

    Args:
        corr_id: Correlation ID (generates new one if None)

    Returns:
        The correlation ID (new or existing)
    """
    if corr_id is None:
        corr_id = str(uuid.uuid4())[:8]
    _correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> str | None:
    """Get current correlation ID."""
    return _correlation_id.get()


def set_experiment_name(name: str | None) -> None:
    """Set experiment name for current context.

    Args:
        name: Experiment name (e.g., "hybrid_v2", "gnn_ablation")
    """
    _experiment_name.set(name)


def get_experiment_name() -> str | None:
    """Get current experiment name."""
    return _experiment_name.get()


def set_dataset_version(version: str | None) -> None:
    """Set dataset version for current context.

    Args:
        version: Dataset version (e.g., "v2024-W52", "pairs_large_v2")
    """
    _dataset_version.set(version)


def get_dataset_version() -> str | None:
    """Get current dataset version."""
    return _dataset_version.get()


def set_model_architecture(arch: str | None) -> None:
    """Set model architecture for current context.

    Args:
        arch: Model architecture (e.g., "GraphSAGE", "E5-base-v2", "hybrid")
    """
    _model_architecture.set(arch)


def get_model_architecture() -> str | None:
    """Get current model architecture."""
    return _model_architecture.get()


def set_git_commit(commit: str | None) -> None:
    """Set git commit hash for current context.

    Args:
        commit: Git commit hash (e.g., "abc1234", auto-detected if None)
    """
    if commit is None:
        commit = _get_git_commit()
    _git_commit.set(commit)


def get_git_commit() -> str | None:
    """Get current git commit hash."""
    return _git_commit.get()


def _get_git_commit() -> str | None:
    """Auto-detect git commit hash from current directory."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


def _get_resource_metrics() -> dict[str, Any]:
    """Get current resource usage metrics (CPU, memory, GPU if available).

    Returns:
        Dictionary with cpu_percent, memory_mb, gpu_utilization (if available)
    """
    metrics: dict[str, Any] = {}

    # CPU and memory via psutil (optional)
    try:
        import psutil

        metrics["cpu_percent"] = round(psutil.cpu_percent(interval=0.1), 1)
        process = psutil.Process()
        metrics["memory_mb"] = round(process.memory_info().rss / (1024 * 1024), 1)
    except ImportError:
        pass
    except Exception:
        pass

    # GPU utilization via nvidia-ml-py (optional)
    try:
        import pynvml

        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count > 0:
            # Get utilization for first GPU
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            metrics["gpu_utilization"] = util.gpu
    except ImportError:
        pass
    except Exception:
        pass

    return metrics


def configure_logging(
    level: int | str | None = None,
    format_str: str | None = None,
    log_file: Path | str | None = None,
    log_dir: Path | str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    force: bool = False,
    enable_progress_formatting: bool = True,
    enable_correlation_ids: bool = True,
) -> None:
    """Configure logging for the application.

    Args:
        level: Logging level (int or string like "INFO")
        format_str: Format string (or "standard", "detailed", "minimal")
        log_file: Path to log file (creates if doesn't exist)
        log_dir: Directory for log files (auto-detects script name)
        max_bytes: Max size for rotating file handler
        backup_count: Number of backup files to keep
        force: Force reconfiguration even if already configured
        enable_progress_formatting: Enable ProgressFormatter
        enable_correlation_ids: Add correlation ID tracking

    Examples:
        # Basic usage (uses env vars or defaults)
        configure_logging()

        # Explicit configuration
        configure_logging(level=logging.DEBUG, format_str="detailed")

        # With file logging
        configure_logging(log_file=Path("logs/app.log"))

        # Auto-detect script name for log file
        configure_logging(log_dir=Path("logs"))
    """
    global _logging_configured

    if _logging_configured and not force:
        return

    # Get configuration from args or environment
    if level is None:
        level = get_log_level()
    elif isinstance(level, str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = level_map.get(level.upper(), logging.INFO)

    if format_str is None:
        format_str = get_log_format()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    if force:
        root_logger.handlers.clear()

    # Only add handlers if they don't exist
    has_console = any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)
    has_file = any(
        isinstance(h, (logging.FileHandler, RotatingFileHandler)) for h in root_logger.handlers
    )

    # Create formatter
    if enable_progress_formatting:
        formatter = ProgressFormatter(format_str)
    else:
        formatter = logging.Formatter(format_str)

    # Add correlation ID filter if enabled
    if enable_correlation_ids:
        corr_filter = CorrelationIDFilter()
    else:
        corr_filter = None

    # Console handler (always add, unless already exists)
    if not has_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        if corr_filter:
            console_handler.addFilter(corr_filter)
        root_logger.addHandler(console_handler)

    # File handler (if requested)
    if log_file or log_dir:
        if log_file:
            log_path = Path(log_file)
        elif log_dir:
            # Auto-detect script name from sys.argv[0]
            script_name = Path(sys.argv[0]).stem if sys.argv else "app"
            log_path = Path(log_dir) / f"{script_name}.log"
        else:
            log_path = None

        if log_path and not has_file:
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Use rotating file handler to prevent unbounded growth
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            if corr_filter:
                file_handler.addFilter(corr_filter)
            root_logger.addHandler(file_handler)

    _logging_configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance with proper configuration.

    This ensures logging is configured before returning a logger.
    Use this instead of logging.getLogger() directly.

    Args:
        name: Logger name (defaults to calling module)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Message")
    """
    if not _logging_configured:
        configure_logging()

    if name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "root")
        else:
            name = "root"

    return logging.getLogger(name)


def log_exception(
    logger: logging.Logger,
    message: str,
    exc: Exception,
    level: Literal["error", "warning", "critical"] = "error",
    include_context: bool = True,
) -> None:
    """Log exception with full traceback and context.

    Args:
        logger: Logger instance
        message: Error message
        exc: Exception object
        level: Log level
        include_context: Include correlation ID and context in message
    """
    error_msg = message
    if include_context:
        corr_id = get_correlation_id()
        if corr_id:
            error_msg = f"[{corr_id}] {error_msg}"

    # Log with full traceback
    log_method = getattr(logger, level, logger.error)
    log_method(f"{error_msg}: {exc}", exc_info=True)


def log_progress(
    logger: logging.Logger,
    stage: str,
    progress: str | float | None = None,
    total: float | None = None,
    component: str | None = None,
    **metadata: Any,
) -> None:
    """Log progress update in parseable format for monitoring scripts.

    This creates logs that monitoring scripts can easily parse:
    - "[PROGRESS] stage=value progress=X/Y pct=Z%" format
    - Includes correlation ID if available
    - Adds metadata as structured key=value fields
    - Automatically calculates elapsed time and ETA if progress/total provided

    Args:
        logger: Logger instance
        stage: Stage name (e.g., "epoch", "batch", "data_loading")
        progress: Current progress (number or description)
        total: Total expected (for percentage calculation)
        component: Component name (e.g., "gnn", "cooccurrence", "instruction_tuned", "fusion")
        **metadata: Additional metadata to include (will be formatted as key=value)
    """
    import time

    # Track start time for this stage (thread-safe)
    stage_key = f"{get_correlation_id() or 'default'}:{stage}"
    with _training_start_times_lock:
        if stage_key not in _training_start_times:
            _training_start_times[stage_key] = time.time()
        start_time = _training_start_times[stage_key]
    elapsed = time.time() - start_time

    # Build structured message parts
    parts = [f"stage={stage}"]

    # Add component if specified
    if component:
        parts.append(f"component={component}")

    # Add progress information
    if isinstance(progress, (int, float)) and total:
        pct = (progress / total) * 100
        parts.append(f"progress={progress}/{total}")
        parts.append(f"pct={pct:.1f}%")

        # Calculate ETA if we have progress
        if progress > 0 and elapsed > 0:
            rate = progress / elapsed
            remaining = (total - progress) / rate if rate > 0 else 0
            eta_seconds = int(remaining)
            if eta_seconds < 60:
                eta_str = f"{eta_seconds}s"
            elif eta_seconds < 3600:
                eta_str = f"{eta_seconds // 60}m{eta_seconds % 60}s"
            else:
                hours = eta_seconds // 3600
                mins = (eta_seconds % 3600) // 60
                eta_str = f"{hours}h{mins}m"
            parts.append(f"eta={eta_str}")

            # Add throughput if applicable
            if stage in ("epoch", "batch"):
                throughput = rate
                if stage == "epoch":
                    parts.append(f"epochs_per_hour={throughput * 3600:.2f}")
                else:
                    parts.append(f"batches_per_sec={throughput:.2f}")
    elif progress:
        parts.append(f"progress={progress}")

    # Add elapsed time
    elapsed_str = str(timedelta(seconds=int(elapsed))).split(".")[0]  # HH:MM:SS format
    parts.append(f"elapsed={elapsed_str}")

    # Add metadata as key=value pairs (structured, easy to parse)
    # Limit to prevent extremely long log lines
    MAX_METADATA_ITEMS = 15
    if metadata:
        metadata_items = list(metadata.items())[:MAX_METADATA_ITEMS]
        for k, v in metadata_items:
            # Format values appropriately
            if isinstance(v, float):
                # Use scientific notation for very small/large numbers
                if abs(v) < 0.001 or abs(v) > 1000:
                    parts.append(f"{k}={v:.3e}")
                else:
                    parts.append(f"{k}={v:.4f}")
            elif isinstance(v, str):
                # Escape special characters: spaces, equals, quotes
                # Replace spaces with underscores, equals with _eq_
                v_escaped = str(v).replace(" ", "_").replace("=", "_eq_").replace('"', "'")
                # Truncate very long values
                if len(v_escaped) > 50:
                    v_escaped = v_escaped[:47] + "..."
                parts.append(f"{k}={v_escaped}")
            else:
                parts.append(f"{k}={v}")

        if len(metadata) > MAX_METADATA_ITEMS:
            parts.append(f"...({len(metadata) - MAX_METADATA_ITEMS}_more)")

    # Add context fields if available
    context_parts = []
    corr_id = get_correlation_id()
    if corr_id:
        context_parts.append(f"corr_id={corr_id}")

    exp_name = get_experiment_name()
    if exp_name:
        context_parts.append(f"experiment={exp_name}")

    # Add hostname for distributed training
    hostname = _get_hostname()
    if hostname and hostname != "unknown":
        context_parts.append(f"host={hostname}")

    # Add process ID for debugging
    context_parts.append(f"pid={os.getpid()}")

    # Add optional context fields
    dataset_ver = get_dataset_version()
    if dataset_ver:
        context_parts.append(f"dataset_version={dataset_ver}")

    model_arch = get_model_architecture()
    if model_arch:
        context_parts.append(f"model_architecture={model_arch}")

    git_commit = get_git_commit()
    if git_commit:
        context_parts.append(f"git_commit={git_commit}")

    # Add resource metrics (optional, only if available)
    resource_metrics = _get_resource_metrics()
    if resource_metrics:
        if "cpu_percent" in resource_metrics:
            context_parts.append(f"cpu_percent={resource_metrics['cpu_percent']}")
        if "memory_mb" in resource_metrics:
            context_parts.append(f"memory_mb={resource_metrics['memory_mb']}")
        if "gpu_utilization" in resource_metrics:
            context_parts.append(f"gpu_utilization={resource_metrics['gpu_utilization']}")

    # Build final message: prefix, then context, then data
    if context_parts:
        msg = f"[PROGRESS] {' '.join(context_parts)} " + " ".join(parts)
    else:
        msg = "[PROGRESS] " + " ".join(parts)

    logger.info(msg)


def log_checkpoint(
    logger: logging.Logger,
    checkpoint_name: str,
    checkpoint_path: Path | str | None = None,
    component: str | None = None,
    **metadata: Any,
) -> None:
    """Log checkpoint save in parseable format.

    Args:
        logger: Logger instance
        checkpoint_name: Name of checkpoint (e.g., "epoch_10", "final")
        checkpoint_path: Path to checkpoint file
        component: Component name (e.g., "gnn", "cooccurrence", "instruction_tuned", "fusion")
        **metadata: Additional metadata (formatted as key=value)
    """
    # Build structured message parts
    parts = [f"name={checkpoint_name}"]

    # Add component if specified (from parameter or metadata)
    if component:
        parts.append(f"component={component}")
    elif "component" in metadata:
        parts.append(f"component={metadata['component']}")

    if checkpoint_path:
        parts.append(f"path={checkpoint_path}")
        # Add file size if path exists
        try:
            path_obj = Path(checkpoint_path)
            if path_obj.exists():
                size_mb = path_obj.stat().st_size / (1024 * 1024)
                parts.append(f"size_mb={size_mb:.2f}")
        except (OSError, ValueError):
            pass

    # Add checkpoint timestamp
    checkpoint_time = datetime.now(UTC).isoformat()
    parts.append(f"checkpoint_time={checkpoint_time}")

    # Add metadata as key=value pairs
    if metadata:
        for k, v in metadata.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.4f}")
            else:
                parts.append(f"{k}={v}")

    # Add context fields if available
    context_parts = []
    corr_id = get_correlation_id()
    if corr_id:
        context_parts.append(f"corr_id={corr_id}")

    exp_name = get_experiment_name()
    if exp_name:
        context_parts.append(f"experiment={exp_name}")

    # Add hostname for distributed training
    hostname = _get_hostname()
    if hostname and hostname != "unknown":
        context_parts.append(f"host={hostname}")

    # Add process ID for debugging
    context_parts.append(f"pid={os.getpid()}")

    # Add optional context fields
    dataset_ver = get_dataset_version()
    if dataset_ver:
        context_parts.append(f"dataset_version={dataset_ver}")

    model_arch = get_model_architecture()
    if model_arch:
        context_parts.append(f"model_architecture={model_arch}")

    git_commit = get_git_commit()
    if git_commit:
        context_parts.append(f"git_commit={git_commit}")

    # Build final message: prefix, then context, then data
    if context_parts:
        msg = f"[CHECKPOINT] {' '.join(context_parts)} " + " ".join(parts)
    else:
        msg = "[CHECKPOINT] " + " ".join(parts)

    logger.info(msg)


# Convenience function for scripts
def setup_script_logging(
    script_name: str | None = None,
    log_dir: Path | str | None = None,
    level: int | str | None = None,
    correlation_id: str | None = None,
    experiment_name: str | None = None,
    dataset_version: str | None = None,
    model_architecture: str | None = None,
    git_commit: str | None = None,
    auto_detect_git: bool = True,
) -> logging.Logger:
    """Setup logging for a script with auto-detection.

    This is the recommended way to set up logging in scripts.
    It automatically:
    - Configures logging with sensible defaults
    - Sets up file logging if log_dir is provided
    - Generates a correlation ID for tracking
    - Logs startup message with correlation ID

    Args:
        script_name: Name of script (auto-detected from __file__ if None)
        log_dir: Directory for log files (creates script_name.log)
        level: Logging level (defaults to INFO)
        correlation_id: Correlation ID (generates if None)
        experiment_name: Experiment name for tracking
        dataset_version: Dataset version (e.g., "v2024-W52")
        model_architecture: Model architecture (e.g., "GraphSAGE", "hybrid")
        git_commit: Git commit hash (auto-detected if None and auto_detect_git=True)
        auto_detect_git: Automatically detect git commit hash

    Returns:
        Configured logger instance

    Example:
        # At the top of a script
        logger = setup_script_logging(log_dir=Path("logs"))
        logger.info("Starting script...")
    """
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

    configure_logging(level=level, log_dir=log_dir)

    # Set correlation ID
    if correlation_id is None:
        correlation_id = set_correlation_id()
    else:
        set_correlation_id(correlation_id)

    # Set experiment name if provided
    if experiment_name:
        set_experiment_name(experiment_name)

    # Set optional context fields
    if dataset_version:
        set_dataset_version(dataset_version)

    if model_architecture:
        set_model_architecture(model_architecture)

    if git_commit or auto_detect_git:
        set_git_commit(git_commit)

    if script_name:
        logger = get_logger(script_name)
    else:
        # Auto-detect from script path
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            script_path = frame.f_back.f_globals.get("__file__", "script")
            script_name = Path(script_path).stem
        else:
            script_name = "script"
        logger = get_logger(script_name)

    # Log startup with correlation ID
    logger.info(f"Starting {script_name} [correlation_id={correlation_id}]")

    return logger
