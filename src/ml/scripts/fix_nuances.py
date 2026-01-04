"""Utility functions for safe operations and edge case handling.

Provides functions to handle common edge cases:
- Safe cache key generation (hash-based, collision-resistant)
- Safe division (zero-division protection)
- Numeric range validation
- Path sanitization
- Type-safe operations
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def safe_cache_key(
    query: str,
    judge_id: int,
    use_case: str | None = None,
    game: str | None = None,
    use_hash: bool = True,
) -> str:
    """
    Generate a safe, collision-resistant cache key.

    Uses hash-based approach to prevent collisions and handle special characters.

    Args:
        query: Query string
        judge_id: Judge identifier
        use_case: Optional use case string
        game: Optional game string
        use_hash: If True, use hash-based key (collision-resistant). If False, use sanitized string.

    Returns:
        Safe cache key string
    """
    # Normalize inputs
    safe_query = str(query).strip()[:500]  # Limit length
    safe_use_case = str(use_case or "").strip()[:100]
    safe_game = str(game or "").strip()[:50]

    if use_hash:
        # Create hash-based key to prevent collisions
        key_string = f"label_{safe_query}_{safe_use_case}_{safe_game}_{judge_id}"
        key_hash = hashlib.sha256(key_string.encode("utf-8")).hexdigest()[:32]

        # Include readable prefix for debugging (sanitized)
        safe_prefix = safe_query.replace("/", "_").replace("\\", "_").replace(":", "_")[:50]
        return f"label_{safe_prefix}_{key_hash}"
    else:
        # Fallback: sanitized string (less collision-resistant but more readable)
        safe_query_clean = safe_query.replace("/", "_").replace("\\", "_").replace(":", "_")[:200]
        safe_use_case_clean = (
            safe_use_case.replace("/", "_").replace("\\", "_").replace(":", "_")[:50]
        )
        safe_game_clean = safe_game.replace("/", "_").replace("\\", "_").replace(":", "_")[:20]
        return f"label_{safe_query_clean}_{safe_use_case_clean}_{safe_game_clean}_{judge_id}"


def safe_division(
    numerator: float | int,
    denominator: float | int | None,
    default: float = 0.0,
    name: str = "division",
) -> float:
    """
    Safe division that handles zero denominator.

    Args:
        numerator: Numerator value
        denominator: Denominator value (can be None or 0)
        default: Value to return if denominator is 0 or None
        name: Name for error messages (optional)

    Returns:
        Result of division, or default if denominator is 0/None
    """
    if denominator is None or denominator == 0:
        return default
    try:
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        # Handle non-numeric inputs gracefully
        return default


def validate_numeric_range(
    value: float | int,
    min_val: float,
    max_val: float,
    name: str = "value",
    clamp: bool = False,
) -> float:
    """
    Validate that a numeric value is in the expected range.

    Args:
        value: Value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        name: Name for error messages
        clamp: If True, clamp to range instead of raising error

    Returns:
        Validated (and optionally clamped) value

    Raises:
        ValueError: If value is outside range and clamp=False
    """
    try:
        float_val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} ({value}) is not a valid number")

    if clamp:
        return max(min_val, min(max_val, float_val))
    elif float_val < min_val or float_val > max_val:
        raise ValueError(f"{name} ({float_val}) is outside valid range [{min_val}, {max_val}]")

    return float_val


def sanitize_path(path: str | Path, max_length: int = 500) -> str:
    """
    Sanitize a path string to prevent issues with special characters.

    Args:
        path: Path to sanitize
        max_length: Maximum length of sanitized path

    Returns:
        Sanitized path string
    """
    path_str = str(path)
    # Replace problematic characters
    sanitized = path_str.replace("\x00", "").replace("\r", "").replace("\n", "")
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def safe_json_load(
    path: Path, default: dict[str, Any] | list[Any] | None = None
) -> dict[str, Any] | list[Any]:
    """
    Safely load JSON with comprehensive error handling.

    Args:
        path: Path to JSON file
        default: Default value to return on error

    Returns:
        Loaded JSON data, or default if loading fails
    """
    import json

    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"JSON file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        if default is not None:
            return default
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    except OSError as e:
        if default is not None:
            return default
        raise OSError(f"Failed to read {path}: {e}") from e


def safe_json_dump(data: dict[str, Any] | list[Any], path: Path, indent: int = 2) -> None:
    """
    Safely write JSON with error handling and atomic writes.

    Args:
        data: Data to write
        path: Path to write to
        indent: JSON indentation

    Raises:
        IOError: If writing fails
    """
    import json

    # Write to temp file first, then rename (atomic on most filesystems)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        temp_path.replace(path)  # Atomic rename
    except OSError as e:
        # Clean up temp file on error
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise OSError(f"Failed to write JSON to {path}: {e}") from e
    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise


def type_safe_get(data: dict[str, Any], key: str, expected_type: type, default: Any = None) -> Any:
    """
    Type-safe dictionary access with validation.

    Args:
        data: Dictionary to access
        key: Key to look up
        expected_type: Expected type of value
        default: Default value if key missing or wrong type

    Returns:
        Value if present and correct type, else default
    """
    if key not in data:
        return default

    value = data[key]
    if isinstance(value, expected_type):
        return value

    # Try type conversion for numeric types
    if expected_type in (int, float) and isinstance(value, (int, float, str)):
        try:
            return expected_type(value)
        except (ValueError, TypeError):
            return default

    return default
