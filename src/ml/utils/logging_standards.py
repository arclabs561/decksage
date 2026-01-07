#!/usr/bin/env python3
"""
Logging standards and utilities for consistent logging across the codebase.

Defines when to use different log levels and provides helper functions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LoggingStandards:
    """
    Standards for when to use different log levels.

    ERROR:   System errors, failures that prevent functionality
            - Failed to load critical assets (embeddings, graph)
            - Data corruption or invalid format
            - API failures that break functionality
            - Exceptions that are caught but indicate bugs

    WARNING: Recoverable issues, degraded functionality
            - Optional dependencies not available
            - Missing optional data (e.g., text embeddings)
            - Performance issues (slow operations)
            - Deprecated feature usage
            - Configuration issues that have fallbacks

    INFO:    Important state changes, progress updates
            - Module initialization
            - Asset loading start/complete
            - Major operation start/complete
            - Configuration loaded
            - Significant state changes

    DEBUG:   Detailed diagnostic information
            - Function entry/exit
            - Intermediate computation results
            - Cache hits/misses
            - Detailed state information
            - Verbose operation details
    """

    @staticmethod
    def log_error(message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log an error-level message."""
        logger.error(message, exc_info=exc_info, extra=kwargs)

    @staticmethod
    def log_warning(message: str, **kwargs: Any) -> None:
        """Log a warning-level message."""
        logger.warning(message, extra=kwargs)

    @staticmethod
    def log_info(message: str, **kwargs: Any) -> None:
        """Log an info-level message."""
        logger.info(message, extra=kwargs)

    @staticmethod
    def log_debug(message: str, **kwargs: Any) -> None:
        """Log a debug-level message."""
        logger.debug(message, extra=kwargs)

    @staticmethod
    def log_asset_load(asset_name: str, status: str, **kwargs: Any) -> None:
        """
        Log asset loading with consistent format.

        Args:
            asset_name: Name of asset being loaded
            status: "start", "complete", "failed", "skipped"
            **kwargs: Additional context
        """
        if status == "start":
            logger.info(f"Loading {asset_name}...", extra=kwargs)
        elif status == "complete":
            logger.info(f"Loaded {asset_name}", extra=kwargs)
        elif status == "failed":
            logger.error(f"Failed to load {asset_name}", extra=kwargs)
        elif status == "skipped":
            logger.warning(f"Skipped loading {asset_name}", extra=kwargs)
        else:
            logger.info(f"{asset_name}: {status}", extra=kwargs)

    @staticmethod
    def log_operation(operation: str, status: str, **kwargs: Any) -> None:
        """
        Log operation with consistent format.

        Args:
            operation: Name of operation
            status: "start", "complete", "failed"
            **kwargs: Additional context
        """
        if status == "start":
            logger.info(f"Starting {operation}...", extra=kwargs)
        elif status == "complete":
            logger.info(f"Completed {operation}", extra=kwargs)
        elif status == "failed":
            logger.error(f"Failed {operation}", extra=kwargs)
        else:
            logger.info(f"{operation}: {status}", extra=kwargs)




