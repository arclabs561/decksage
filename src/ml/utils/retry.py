"""Retry utilities for handling transient failures."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar


try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry (exception, attempt_number)

    Example:
        @retry_with_backoff(max_retries=3, initial_delay=2.0)
        def fetch_data():
            # May fail transiently
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        else:
                            logger.warning(
                                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                                f"Retrying in {delay:.1f}s..."
                            )

                        time.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
                        raise

            # Should never reach here, but type checker needs it
            raise last_exception  # type: ignore

        return wrapper

    return decorator


def retry_command(
    command: list[str],
    max_retries: int = 3,
    initial_delay: float = 2.0,
    **kwargs: Any,
) -> tuple[int, str, str]:
    """
    Execute a command with retry logic.

    Args:
        command: Command to execute (list of strings)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        **kwargs: Additional arguments to pass to subprocess.run

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    import subprocess

    delay = initial_delay
    last_result = None

    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                **kwargs,
            )

            if result.returncode == 0:
                return (result.returncode, result.stdout, result.stderr)

            last_result = result

            if attempt < max_retries:
                logger.warning(
                    f"Command failed (attempt {attempt + 1}/{max_retries + 1}): {' '.join(command)}"
                )
                logger.warning(f"  Return code: {result.returncode}")
                logger.warning(f"  Stderr: {result.stderr[:200]}")
                logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(f"Command failed after {max_retries + 1} attempts")
                break

        except Exception as e:
            last_result = type("Result", (), {"returncode": 1, "stdout": "", "stderr": str(e)})()
            if attempt < max_retries:
                logger.warning(f"Command exception (attempt {attempt + 1}/{max_retries + 1}): {e}")
                logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(f"Command exception after {max_retries + 1} attempts: {e}")
                break

    # Return last result
    if last_result:
        return (last_result.returncode, last_result.stdout, last_result.stderr)

    return (1, "", "All retry attempts failed")
