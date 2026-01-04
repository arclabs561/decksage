"""
Query history tracking for API endpoints.

Tracks user queries for analytics and personalization.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ..utils.paths import PATHS
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    PATHS = None


def get_query_history_path() -> Path:
    """Get path to query history storage file."""
    if PATHS:
        history_dir = PATHS.DATA_DIR / "analytics"
    else:
        history_dir = Path("data/analytics")
    
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / "query_history.jsonl"


def log_query(
    endpoint: str,
    query: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Log a query for analytics.
    
    Non-blocking: failures don't affect API performance.
    Note: File I/O is not thread-safe - for production, use database or queue.
    """
    history_path = get_query_history_path()
    
    # Validate and sanitize input
    if not endpoint or not query:
        logger.debug("Skipping query log: missing endpoint or query")
        return
    
    # Limit query length to prevent abuse
    query = query[:1000] if len(query) > 1000 else query
    
    # Sanitize metadata (remove any non-serializable items)
    safe_metadata = {}
    if metadata:
        for k, v in metadata.items():
            try:
                json.dumps(v)  # Test if serializable
                safe_metadata[str(k)[:100]] = v  # Limit key length
            except (TypeError, ValueError):
                safe_metadata[str(k)[:100]] = str(v)[:500]  # Convert to string
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "endpoint": str(endpoint)[:200],  # Limit endpoint length
        "query": query,
        "user_id": str(user_id)[:100] if user_id else None,  # Limit user_id length
        "session_id": str(session_id)[:100] if session_id else None,  # Limit session_id length
        "metadata": safe_metadata,
    }
    
    try:
        # Use append mode (atomic on most filesystems, but not guaranteed thread-safe)
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, IOError) as e:
        # Non-fatal: log but don't raise
        logger.debug(f"Failed to log query (non-fatal): {e}")
    except Exception as e:
        # Catch-all for any other errors
        logger.debug(f"Unexpected error logging query (non-fatal): {e}")


def get_query_stats(days: int = 7) -> dict[str, Any]:
    """Get query statistics for the last N days."""
    history_path = get_query_history_path()
    
    if not history_path.exists():
        return {
            "total_queries": 0,
            "by_endpoint": {},
            "top_queries": [],
            "unique_users": 0,
        }
    
    cutoff = datetime.now().timestamp() - (days * 86400)
    queries_by_endpoint: dict[str, int] = defaultdict(int)
    query_counts: dict[str, int] = defaultdict(int)
    users: set[str] = set()
    total = 0
    
    try:
        with open(history_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        entry_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
                        if entry_time >= cutoff:
                            total += 1
                            queries_by_endpoint[entry.get("endpoint", "unknown")] += 1
                            query_counts[entry.get("query", "")] += 1
                            if entry.get("user_id"):
                                users.add(entry["user_id"])
                    except Exception:
                        continue
    except Exception:
        pass
    
    # Top queries
    top_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "total_queries": total,
        "by_endpoint": dict(queries_by_endpoint),
        "top_queries": [{"query": q, "count": c} for q, c in top_queries],
        "unique_users": len(users),
        "period_days": days,
    }

