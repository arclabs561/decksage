"""
Unified Evaluation Results Registry - Production-Ready Version

Implements all priority fixes:
- Priority 1: File locking, atomic writes, schema validation
- Priority 2: SQLite backend, query caching, backup/restore
- Priority 3: Migration system, version validation, archival, bulk operations

Backward compatible with existing JSON-based storage.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..model_registry import ModelRegistry
from ..utils.paths import PATHS


try:
    from filelock import FileLock, Timeout

    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False
    FileLock = None
    Timeout = None

try:
    from pydantic import BaseModel, Field, field_validator

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    # Create minimal stubs for type checking
    class BaseModel:
        def __init__(self, **kwargs):
            pass

        def model_dump(self):
            return {}

    def Field(*args, **kwargs):
        return None

    def field_validator(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

try:
    from .structured_logging import StructuredLogger

    HAS_STRUCTURED_LOGGING = True
except ImportError:
    HAS_STRUCTURED_LOGGING = False
    StructuredLogger = None

try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# Schema version for migration support
SCHEMA_VERSION = 1

# Version format validation patterns
VERSION_PATTERNS = [
    r"^v?\d{4}-W\d{2}$",  # v2026-W01 or 2026-W01
    r"^v?\d{4}-\d{2}-\d{2}$",  # v2026-01-01 or 2026-01-01
    r"^v?\d+\.\d+\.\d+$",  # v1.2.3 or 1.2.3
    r"^test-.*$",  # test-20260101-085347
]


def validate_version_format(version: str) -> bool:
    """Validate version format against standard patterns."""
    return any(re.match(pattern, version) for pattern in VERSION_PATTERNS)


if HAS_PYDANTIC:

    class EvaluationRecord(BaseModel):
        """Pydantic model for evaluation record validation."""

        timestamp: str
        model_type: str = Field(..., min_length=1, max_length=100)
        model_version: str = Field(..., min_length=1, max_length=100)
        model_path: str = Field(..., min_length=1)
        test_set_path: str | None = None
        metrics: dict[str, float] = Field(default_factory=dict)
        full_results: dict[str, Any] = Field(default_factory=dict)
        metadata: dict[str, Any] = Field(default_factory=dict)
        is_production: bool = False

        @field_validator("model_version")
        @classmethod
        def validate_version(cls, v: str) -> str:
            """Validate version format."""
            if not validate_version_format(v):
                logger.warning(
                    f"Version '{v}' doesn't match standard format patterns. "
                    f"Consider using formats like 'v2026-W01' or 'v2026-01-01'"
                )
            return v

        @field_validator("metrics")
        @classmethod
        def validate_metrics(cls, v: dict[str, float]) -> dict[str, float]:
            """Ensure all metric values are finite floats."""
            validated = {}
            for key, value in v.items():
                try:
                    float_val = float(value)
                    if not (float_val == float_val):  # Check for NaN
                        logger.warning(f"Metric {key} is NaN, skipping")
                        continue
                    if not (float("-inf") < float_val < float("inf")):  # Check for inf
                        logger.warning(f"Metric {key} is infinite, skipping")
                        continue
                    validated[key] = float_val
                except (ValueError, TypeError):
                    logger.warning(f"Invalid metric value for {key}: {value}")
            return validated


class QueryCache:
    """In-memory cache for query results with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize query cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 5 minutes)
        """
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: dict[str, tuple[Any, datetime]] = {}

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if datetime.now() - timestamp > self.ttl:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        """Set cache value with current timestamp."""
        self._cache[key] = (value, datetime.now())

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        import fnmatch

        keys_to_remove = [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_remove:
            del self._cache[key]


class SQLiteBackend:
    """SQLite backend for evaluation storage with proper indexing."""

    def __init__(self, db_path: Path | str):
        """
        Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema with indices."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    model_type TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    model_path TEXT NOT NULL,
                    test_set_path TEXT,
                    metrics TEXT NOT NULL,  -- JSON string
                    full_results TEXT NOT NULL,  -- JSON string
                    metadata TEXT NOT NULL,  -- JSON string
                    is_production INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(model_type, model_version)
                )
            """)

            # Create indices for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_model_type ON evaluations(model_type)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON evaluations(timestamp DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_production ON evaluations(is_production, model_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_version ON evaluations(model_type, model_version)"
            )

            conn.commit()

    def insert(self, record: dict[str, Any]) -> int:
        """Insert evaluation record, returns row ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO evaluations
                (timestamp, model_type, model_version, model_path, test_set_path,
                 metrics, full_results, metadata, is_production, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["timestamp"],
                    record["model_type"],
                    record["model_version"],
                    record["model_path"],
                    record.get("test_set_path"),
                    json.dumps(record["metrics"]),
                    json.dumps(record["full_results"]),
                    json.dumps(record.get("metadata", {})),
                    1 if record.get("is_production", False) else 0,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list(
        self, model_type: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """List evaluations with optional filtering."""
        query = "SELECT * FROM evaluations"
        params: list[Any] = []

        if model_type:
            query += " WHERE model_type = ?"
            params.append(model_type)

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        evaluations = []
        for row in rows:
            eval_dict = {
                "timestamp": row["timestamp"],
                "model_type": row["model_type"],
                "model_version": row["model_version"],
                "model_path": row["model_path"],
                "test_set_path": row["test_set_path"],
                "metrics": json.loads(row["metrics"]),
                "full_results": json.loads(row["full_results"]),
                "metadata": json.loads(row["metadata"]),
                "is_production": bool(row["is_production"]),
            }
            evaluations.append(eval_dict)

        return evaluations

    def get(self, model_type: str, model_version: str) -> dict[str, Any] | None:
        """Get specific evaluation by type and version."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM evaluations WHERE model_type = ? AND model_version = ?",
                (model_type, model_version),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "timestamp": row["timestamp"],
            "model_type": row["model_type"],
            "model_version": row["model_version"],
            "model_path": row["model_path"],
            "test_set_path": row["test_set_path"],
            "metrics": json.loads(row["metrics"]),
            "full_results": json.loads(row["full_results"]),
            "metadata": json.loads(row["metadata"]),
            "is_production": bool(row["is_production"]),
        }

    def count(self, model_type: str | None = None) -> int:
        """Count evaluations."""
        query = "SELECT COUNT(*) FROM evaluations"
        params: list[Any] = []

        if model_type:
            query += " WHERE model_type = ?"
            params.append(model_type)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()[0]


class EvaluationRegistry:
    """
    Production-ready evaluation registry with all priority fixes.

    Features:
    - File locking for concurrent writes
    - Atomic writes (temp file + rename)
    - Schema validation (Pydantic models)
    - SQLite backend with indexing
    - Query caching with TTL
    - Backup/restore utilities
    - Migration system
    - Version format validation
    - Evaluation archival
    - Bulk import/export
    """

    def __init__(
        self,
        registry_path: Path | str | None = None,
        log_path: Path | str | None = None,
        results_dir: Path | str | None = None,
        use_sqlite: bool = True,
        sqlite_path: Path | str | None = None,
        cache_ttl: int = 300,
    ):
        """
        Initialize evaluation registry.

        Args:
            registry_path: Path to model registry JSON
            log_path: Path to structured log JSONL
            results_dir: Directory for versioned evaluation results
            use_sqlite: Whether to use SQLite backend (default: True)
            sqlite_path: Path to SQLite database (default: experiments/evaluation_registry.db)
            cache_ttl: Cache TTL in seconds (default: 300)
        """
        self.model_registry = ModelRegistry(registry_path)
        if HAS_STRUCTURED_LOGGING:
            default_log_path = PATHS.experiments / "EXPERIMENT_LOG_CANONICAL.jsonl"
            self.structured_logger = StructuredLogger(log_path or default_log_path)
            self.log_path = log_path or default_log_path
        else:
            self.structured_logger = None
            self.log_path = None

        self.results_dir = (
            Path(results_dir) if results_dir else PATHS.experiments / "evaluation_results"
        )
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # SQLite backend
        self.use_sqlite = use_sqlite
        if use_sqlite:
            if sqlite_path is None:
                sqlite_path = PATHS.experiments / "evaluation_registry.db"
            self.sqlite_backend = SQLiteBackend(sqlite_path)
        else:
            self.sqlite_backend = None

        # Query cache
        self.cache = QueryCache(ttl_seconds=cache_ttl)

        # File locking
        self._lock_timeout = 10  # seconds

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        """
        Write file atomically using temp file + rename.

        Args:
            path: Target file path
            data: Data to write (will be JSON-serialized)
        """
        temp_path = path.with_suffix(".tmp")
        try:
            # Write to temp file
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            # Atomic rename (POSIX-compliant)
            temp_path.replace(path)
        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def _write_with_lock(self, path: Path, data: dict[str, Any]) -> None:
        """
        Write file with file locking for concurrent access.

        Args:
            path: Target file path
            data: Data to write
        """
        if not HAS_FILELOCK:
            # Fallback to atomic write without locking
            logger.warning("filelock not available, using atomic write without locking")
            self._atomic_write(path, data)
            return

        lock_path = path.with_suffix(".lock")
        try:
            with FileLock(lock_path, timeout=self._lock_timeout):
                self._atomic_write(path, data)
        except Timeout:
            raise RuntimeError(
                f"Could not acquire lock for {path} within {self._lock_timeout} seconds"
            )

    def record_evaluation(
        self,
        model_type: str,
        model_version: str,
        model_path: Path | str,
        evaluation_results: dict[str, Any],
        test_set_path: Path | str | None = None,
        metadata: dict[str, Any] | None = None,
        is_production: bool = False,
        save_versioned: bool = True,
    ) -> Path:
        """
        Record evaluation results and register model version.

        All priority fixes applied:
        - Schema validation (Pydantic)
        - Version format validation
        - Atomic writes
        - File locking
        - SQLite storage (if enabled)
        """
        timestamp = datetime.now().isoformat()

        # Validate version format (warn but don't fail)
        if not validate_version_format(model_version):
            logger.warning(
                f"Version '{model_version}' doesn't match standard format. "
                f"Consider using formats like 'v2026-W01' or 'v2026-01-01'"
            )

        # Extract key metrics
        metrics = self._extract_metrics(evaluation_results)

        # Prepare full evaluation record
        evaluation_record = {
            "timestamp": timestamp,
            "model_type": model_type,
            "model_version": model_version,
            "model_path": str(model_path),
            "test_set_path": str(test_set_path) if test_set_path else None,
            "metrics": metrics,
            "full_results": evaluation_results,
            "metadata": metadata or {},
            "is_production": is_production,
        }

        # Schema validation (if Pydantic available)
        if HAS_PYDANTIC:
            try:
                validated = EvaluationRecord(**evaluation_record)
                evaluation_record = validated.model_dump()
            except Exception as e:
                logger.error(f"Schema validation failed: {e}")
                raise ValueError(f"Invalid evaluation record: {e}") from e

        # Save to SQLite (if enabled)
        if self.use_sqlite and self.sqlite_backend:
            try:
                self.sqlite_backend.insert(evaluation_record)
                logger.debug(f"Saved evaluation to SQLite: {model_type} v{model_version}")
            except Exception as e:
                logger.warning(f"Failed to save to SQLite: {e}, falling back to JSON")

        # Save versioned results file (with locking and atomic writes)
        if save_versioned:
            results_file = self.results_dir / f"{model_type}_evaluation_v{model_version}.json"
        else:
            results_file = self.results_dir / f"{model_type}_evaluation_latest.json"

        try:
            self._write_with_lock(results_file, evaluation_record)
            logger.info(f"Saved evaluation results: {results_file}")
        except Exception as e:
            logger.error(f"Failed to save evaluation file: {e}")
            raise

        # Register model in registry (with locking)
        try:
            registry_path = self.model_registry.registry_path
            registry_data = self.model_registry._registry.copy()
            registry_data["models"][f"{model_type}_{model_version}"] = {
                "model_type": model_type,
                "version": model_version,
                "path": str(model_path),
                "registered_at": datetime.utcnow().isoformat() + "Z",
                "metrics": metrics,
                "metadata": {
                    **(metadata or {}),
                    "test_set_path": str(test_set_path) if test_set_path else None,
                    "evaluation_timestamp": timestamp,
                },
                "is_production": is_production,
            }

            # Handle production model promotion
            if is_production:
                for key, model in registry_data["models"].items():
                    if (
                        model["model_type"] == model_type
                        and model["version"] != model_version
                        and model.get("is_production", False)
                    ):
                        model["is_production"] = False

            registry_data["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"
            self._write_with_lock(registry_path, registry_data)
            self.model_registry._registry = registry_data
            logger.info(f"Registered model: {model_type}_{model_version}")
        except Exception as e:
            logger.warning(f"Failed to register model in registry: {e}")

        # Log to structured log (if available)
        if self.structured_logger:
            try:
                self.structured_logger.log_event(
                    event_type="evaluation",
                    message=f"Evaluation recorded: {model_type} v{model_version}",
                    level="info",
                    model_type=model_type,
                    model_version=model_version,
                    metrics=metrics,
                    results_file=str(results_file),
                )
            except Exception as e:
                logger.warning(f"Failed to log to structured log: {e}")

        # Invalidate cache
        self.cache.invalidate_pattern(f"list:*")
        self.cache.invalidate_pattern(f"get:{model_type}:*")

        return results_file

    def _extract_metrics(self, results: dict[str, Any]) -> dict[str, float]:
        """Extract key metrics from evaluation results."""
        metrics = {}

        # Direct metrics (top-level)
        if "p_at_10" in results:
            metrics["p_at_10"] = float(results["p_at_10"])
        if "p_at_5" in results:
            metrics["p_at_5"] = float(results["p_at_5"])
        if "mrr" in results:
            metrics["mrr"] = float(results["mrr"])
        if "ndcg" in results:
            metrics["ndcg"] = float(results["ndcg"])

        # Summary metrics
        if "summary" in results:
            summary = results["summary"]
            if "avg_p_at_10" in summary:
                metrics["p_at_10"] = float(summary["avg_p_at_10"])
            if "avg_p_at_5" in summary:
                metrics["p_at_5"] = float(summary["avg_p_at_5"])
            if "avg_mrr" in summary:
                metrics["mrr"] = float(summary["avg_mrr"])
            if "avg_ndcg" in summary:
                metrics["ndcg"] = float(summary["avg_ndcg"])
            if "total_queries" in summary:
                metrics["total_queries"] = float(summary["total_queries"])
            if "evaluated" in summary:
                metrics["evaluated"] = float(summary["evaluated"])

        # Overall metrics
        if "overall" in results:
            overall = results["overall"]
            if "p_at_10" in overall:
                metrics["p_at_10"] = float(overall["p_at_10"])
            if "p_at_5" in overall:
                metrics["p_at_5"] = float(overall["p_at_5"])
            if "mrr" in overall:
                metrics["mrr"] = float(overall["mrr"])
            if "ndcg_at_10" in overall:
                metrics["ndcg"] = float(overall["ndcg_at_10"])

        # Component-specific metrics
        if "components" in results:
            for component, comp_results in results["components"].items():
                if isinstance(comp_results, dict):
                    if "p_at_10" in comp_results:
                        metrics[f"{component}_p_at_10"] = float(comp_results["p_at_10"])
                    if "mrr" in comp_results:
                        metrics[f"{component}_mrr"] = float(comp_results["mrr"])

        # Downstream task metrics
        if "downstream" in results:
            downstream = results["downstream"]
            if "completion_rate" in downstream:
                metrics["completion_rate"] = float(downstream["completion_rate"])
            if "substitution_accuracy" in downstream:
                metrics["substitution_accuracy"] = float(downstream["substitution_accuracy"])

        if "downstream_tasks" in results:
            downstream = results["downstream_tasks"]
            if "completion_rate" in downstream:
                metrics["completion_rate"] = float(downstream["completion_rate"])
            if "substitution_accuracy" in downstream:
                metrics["substitution_accuracy"] = float(downstream["substitution_accuracy"])

        return metrics

    def list_evaluations(
        self,
        model_type: str | None = None,
        limit: int | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        List all evaluation records with caching.

        Args:
            model_type: Filter by model type (optional)
            limit: Limit number of results (optional)
            use_cache: Whether to use cache (default: True)

        Returns:
            List of evaluation records, sorted by timestamp (newest first)
        """
        # Check cache
        cache_key = f"list:{model_type}:{limit}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        # Use SQLite if available
        if self.use_sqlite and self.sqlite_backend:
            evaluations = self.sqlite_backend.list(model_type=model_type, limit=limit)
        else:
            # Fallback to file-based listing
            evaluations = []
            pattern = (
                "*_evaluation*.json"
                if model_type is None
                else f"{model_type}_evaluation*.json"
            )

            for results_file in sorted(self.results_dir.glob(pattern), reverse=True):
                try:
                    with open(results_file) as f:
                        record = json.load(f)

                    if model_type is not None and record.get("model_type") != model_type:
                        continue

                    if "timestamp" not in record:
                        try:
                            record["timestamp"] = datetime.fromtimestamp(
                                results_file.stat().st_mtime
                            ).isoformat()
                        except (OSError, ValueError):
                            record["timestamp"] = datetime.now().isoformat()

                    evaluations.append(record)
                except Exception as e:
                    logger.warning(f"Failed to load {results_file}: {e}")

            evaluations.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            if limit:
                evaluations = evaluations[:limit]

        # Cache result
        if use_cache:
            self.cache.set(cache_key, evaluations)

        return evaluations

    def get_latest_evaluation(
        self,
        model_type: str,
        is_production: bool = False,
    ) -> dict[str, Any] | None:
        """Get latest evaluation results for a model type."""
        if is_production:
            model = self.model_registry.get_production_model(model_type)
        else:
            versions = self.model_registry.list_versions(model_type)
            if not versions:
                return None
            model = versions[0]

        if not model:
            return None

        version = model["version"]

        # Try SQLite first
        if self.use_sqlite and self.sqlite_backend:
            return self.sqlite_backend.get(model_type, version)

        # Fallback to file
        results_file = self.results_dir / f"{model_type}_evaluation_v{version}.json"
        if results_file.exists():
            with open(results_file) as f:
                return json.load(f)

        return None

    def compare_evaluations(
        self,
        model_type: str,
        version1: str,
        version2: str,
        metric: str = "p_at_10",
    ) -> dict[str, Any] | None:
        """Compare two evaluation versions."""
        comparison = self.model_registry.compare_versions(
            model_type=model_type,
            version1=version1,
            version2=version2,
            metric=metric,
        )

        if comparison:
            # Load full results
            eval1 = None
            eval2 = None

            if self.use_sqlite and self.sqlite_backend:
                eval1 = self.sqlite_backend.get(model_type, version1)
                eval2 = self.sqlite_backend.get(model_type, version2)
            else:
                results1_file = (
                    self.results_dir / f"{model_type}_evaluation_v{version1}.json"
                )
                results2_file = (
                    self.results_dir / f"{model_type}_evaluation_v{version2}.json"
                )

                if results1_file.exists():
                    with open(results1_file) as f:
                        eval1 = json.load(f)
                if results2_file.exists():
                    with open(results2_file) as f:
                        eval2 = json.load(f)

            if eval1:
                comparison["full_results1"] = eval1.get("full_results", {})
            if eval2:
                comparison["full_results2"] = eval2.get("full_results", {})

        return comparison

    def detect_regression(
        self,
        model_type: str,
        current_version: str,
        previous_version: str | None = None,
        threshold_pct: float = -10.0,
    ) -> dict[str, Any] | None:
        """Detect performance regression between versions."""
        if previous_version is None:
            prod_model = self.model_registry.get_production_model(model_type)
            if not prod_model:
                logger.warning(f"No production model found for {model_type}")
                return None
            previous_version = prod_model["version"]

        comparison = self.compare_evaluations(
            model_type=model_type,
            version1=previous_version,
            version2=current_version,
            metric="p_at_10",
        )

        if not comparison:
            return None

        delta_pct = comparison.get("delta_pct", 0.0)

        if delta_pct < threshold_pct:
            regression_report = {
                "regression_detected": True,
                "model_type": model_type,
                "current_version": current_version,
                "previous_version": previous_version,
                "p_at_10_drop_pct": delta_pct,
                "threshold": threshold_pct,
                "comparison": comparison,
                "recommendation": "Consider rollback or investigation",
            }

            if self.structured_logger:
                self.structured_logger.log_event(
                    event_type="regression_detected",
                    message=f"Regression detected: {model_type} v{current_version}",
                    level="warning",
                    **regression_report,
                )

            return regression_report

        return None

    def backup(self, backup_path: Path | str | None = None) -> Path:
        """
        Create backup of registry and evaluation files.

        Args:
            backup_path: Path to backup directory (default: experiments/backups/eval_registry_YYYYMMDD_HHMMSS)

        Returns:
            Path to backup directory
        """
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = PATHS.experiments / "backups" / f"eval_registry_{timestamp}"
        else:
            backup_path = Path(backup_path)

        backup_path.mkdir(parents=True, exist_ok=True)

        # Backup registry
        if self.model_registry.registry_path.exists():
            shutil.copy2(
                self.model_registry.registry_path,
                backup_path / self.model_registry.registry_path.name,
            )

        # Backup SQLite database
        if self.use_sqlite and self.sqlite_backend:
            if self.sqlite_backend.db_path.exists():
                shutil.copy2(
                    self.sqlite_backend.db_path,
                    backup_path / self.sqlite_backend.db_path.name,
                )

        # Backup evaluation results directory
        results_backup = backup_path / "evaluation_results"
        if self.results_dir.exists():
            shutil.copytree(self.results_dir, results_backup, dirs_exist_ok=True)

        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def restore(self, backup_path: Path | str) -> None:
        """
        Restore registry and evaluation files from backup.

        Args:
            backup_path: Path to backup directory
        """
        backup_path = Path(backup_path)

        if not backup_path.exists():
            raise ValueError(f"Backup directory not found: {backup_path}")

        # Restore registry
        registry_backup = backup_path / self.model_registry.registry_path.name
        if registry_backup.exists():
            shutil.copy2(registry_backup, self.model_registry.registry_path)
            self.model_registry._registry = self.model_registry._load_registry()

        # Restore SQLite database
        if self.use_sqlite and self.sqlite_backend:
            db_backup = backup_path / self.sqlite_backend.db_path.name
            if db_backup.exists():
                shutil.copy2(db_backup, self.sqlite_backend.db_path)

        # Restore evaluation results
        results_backup = backup_path / "evaluation_results"
        if results_backup.exists():
            if self.results_dir.exists():
                shutil.rmtree(self.results_dir)
            shutil.copytree(results_backup, self.results_dir)

        # Clear cache
        self.cache.clear()

        logger.info(f"Restored from backup: {backup_path}")

    def archive_evaluations(
        self,
        older_than_days: int = 90,
        archive_path: Path | str | None = None,
        compress: bool = True,
    ) -> list[Path]:
        """
        Archive old evaluations to reduce storage.

        Args:
            older_than_days: Archive evaluations older than this many days
            archive_path: Path to archive directory (default: experiments/archive/evaluations)
            compress: Whether to compress archived files

        Returns:
            List of archived file paths
        """
        if archive_path is None:
            archive_path = PATHS.experiments / "archive" / "evaluations"
        else:
            archive_path = Path(archive_path)

        archive_path.mkdir(parents=True, exist_ok=True)

        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        archived = []

        for results_file in self.results_dir.glob("*_evaluation*.json"):
            try:
                with open(results_file) as f:
                    record = json.load(f)

                record_timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                if record_timestamp < cutoff_date:
                    # Move to archive
                    archive_file = archive_path / results_file.name
                    shutil.move(str(results_file), str(archive_file))

                    if compress:
                        # Compress using gzip
                        import gzip

                        with open(archive_file, "rb") as f_in:
                            with gzip.open(f"{archive_file}.gz", "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        archive_file.unlink()
                        archive_file = Path(f"{archive_file}.gz")

                    archived.append(archive_file)
                    logger.info(f"Archived: {results_file.name} -> {archive_file}")

            except Exception as e:
                logger.warning(f"Failed to archive {results_file}: {e}")

        # Invalidate cache
        self.cache.clear()

        return archived

    def bulk_import(self, evaluations: list[dict[str, Any]]) -> int:
        """
        Bulk import evaluations.

        Args:
            evaluations: List of evaluation record dicts

        Returns:
            Number of successfully imported evaluations
        """
        imported = 0
        for eval_record in evaluations:
            try:
                self.record_evaluation(
                    model_type=eval_record["model_type"],
                    model_version=eval_record["model_version"],
                    model_path=eval_record["model_path"],
                    evaluation_results=eval_record.get("full_results", {}),
                    test_set_path=eval_record.get("test_set_path"),
                    metadata=eval_record.get("metadata", {}),
                    is_production=eval_record.get("is_production", False),
                )
                imported += 1
            except Exception as e:
                logger.warning(f"Failed to import evaluation: {e}")

        return imported

    def bulk_export(
        self,
        output_path: Path | str,
        model_type: str | None = None,
        format: str = "json",
    ) -> Path:
        """
        Bulk export evaluations to file.

        Args:
            output_path: Path to output file
            model_type: Filter by model type (optional)
            format: Export format ('json' or 'jsonl')

        Returns:
            Path to exported file
        """
        output_path = Path(output_path)
        evaluations = self.list_evaluations(model_type=model_type)

        if format == "json":
            with open(output_path, "w") as f:
                json.dump(evaluations, f, indent=2)
        elif format == "jsonl":
            with open(output_path, "w") as f:
                for eval_record in evaluations:
                    f.write(json.dumps(eval_record) + "\n")
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Exported {len(evaluations)} evaluations to {output_path}")
        return output_path

    def migrate_from_json(self) -> int:
        """
        Migrate existing JSON-based evaluations to SQLite.

        Returns:
            Number of evaluations migrated
        """
        if not self.use_sqlite or not self.sqlite_backend:
            raise ValueError("SQLite backend not enabled")

        migrated = 0
        for results_file in self.results_dir.glob("*_evaluation*.json"):
            try:
                with open(results_file) as f:
                    record = json.load(f)

                # Insert into SQLite
                self.sqlite_backend.insert(record)
                migrated += 1
            except Exception as e:
                logger.warning(f"Failed to migrate {results_file}: {e}")

        logger.info(f"Migrated {migrated} evaluations to SQLite")
        return migrated

