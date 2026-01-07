#!/usr/bin/env python3
"""
Evaluation logging and tracking utilities.

Provides structured logging of evaluation runs with metadata, timestamps,
and results. Supports both JSONL (append-only) and JSON (structured) formats.

Integration Options:
- EXPERIMENT_LOG: Write to EXPERIMENT_LOG_CANONICAL.jsonl for unified experiment tracking
- EvaluationRegistry: Bridge to evaluation_registry.db for model-centric queries

Validation:
- Optional Pydantic validation (if available)
- Schema versioning for future migrations
- Read validation for existing files
- Checksum support (optional, via add_checksums.py)

Performance:
- For high-throughput scenarios, use AsyncEvaluationLogger
- Batch writes available in async version
- Database optimization via optimize_evaluation_db.py

See docs/EVALUATION_LOGGING_INTEGRATION.md for usage guidelines.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PATHS

# Optional imports for integrations
try:
    from .evaluation_registry import EvaluationRegistry
    HAS_EVALUATION_REGISTRY = True
except ImportError:
    HAS_EVALUATION_REGISTRY = False
    EvaluationRegistry = None

# Optional Pydantic validation
try:
    from pydantic import BaseModel, Field, field_validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None
    Field = None
    field_validator = None

# Schema version for future migrations
SCHEMA_VERSION = 1


if HAS_PYDANTIC:
    class EvaluationRunRecord(BaseModel):
        """Pydantic model for evaluation run validation."""
        
        schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
        run_id: str = Field(..., min_length=1, max_length=200)
        timestamp: str = Field(..., min_length=1)
        evaluation_type: str = Field(..., min_length=1, max_length=100)
        method: str = Field(..., min_length=1, max_length=100)
        test_set_path: str | None = None
        num_queries: int | None = Field(None, ge=0)
        metrics: dict[str, Any] = Field(default_factory=dict)
        config: dict[str, Any] = Field(default_factory=dict)
        notes: str | None = None
        checksum: str | None = None  # Optional checksum for integrity
        
        @field_validator("timestamp")
        @classmethod
        def validate_timestamp(cls, v: str) -> str:
            """Validate timestamp is ISO format."""
            try:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid timestamp format: {v}")
            return v
        
        @field_validator("metrics")
        @classmethod
        def validate_metrics(cls, v: dict[str, Any]) -> dict[str, Any]:
            """Ensure metrics values are numeric or valid types."""
            validated = {}
            for key, value in v.items():
                if isinstance(value, (int, float, bool, str, type(None))):
                    validated[key] = value
                else:
                    # Skip invalid types
                    pass
            return validated


class EvaluationLogger:
    """
    Logs evaluation runs with metadata and results.
    
    Supports:
    - JSONL format (append-only, one run per line)
    - JSON format (structured, one file per run) - OPTIONAL by default
    - SQLite database (queryable, structured)
    - Optional integration with EXPERIMENT_LOG and EvaluationRegistry
    - Optional Pydantic validation
    - Schema versioning for migrations
    - Read validation for existing files
    
    Performance:
    - For high-throughput (100+ evaluations), use AsyncEvaluationLogger
    - Regular database optimization recommended (monthly)
    """
    
    def __init__(
        self,
        log_dir: Path | None = None,
        use_sqlite: bool = True,
        use_jsonl: bool = True,
        use_json: bool = False,  # Default False to reduce format proliferation
        write_to_experiment_log: bool = False,
        bridge_to_registry: bool = False,
        validate: bool = True,
        validate_on_read: bool = True,
    ):
        """
        Initialize evaluation logger.
        
        Args:
            log_dir: Directory for logs (default: experiments/evaluation_logs)
            use_sqlite: Enable SQLite logging
            use_jsonl: Enable JSONL logging (append-only)
            use_json: Enable JSON logging (one file per run) - Default False
            write_to_experiment_log: Also write to EXPERIMENT_LOG_CANONICAL.jsonl
            bridge_to_registry: Also write to EvaluationRegistry (if available)
            validate: Enable Pydantic validation on write (if available)
            validate_on_read: Enable validation when reading existing files
        """
        self.log_dir = log_dir or (PATHS.experiments / "evaluation_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.use_sqlite = use_sqlite
        self.use_jsonl = use_jsonl
        self.use_json = use_json
        self.write_to_experiment_log = write_to_experiment_log
        self.bridge_to_registry = bridge_to_registry
        self.validate = validate and HAS_PYDANTIC
        self.validate_on_read = validate_on_read and HAS_PYDANTIC
        
        # Initialize optional integrations
        self.experiment_log_path = None
        if self.write_to_experiment_log:
            self.experiment_log_path = PATHS.experiment_log
        
        self.registry = None
        if self.bridge_to_registry:
            try:
                from .evaluation_registry import EvaluationRegistry
                self.registry = EvaluationRegistry()
            except ImportError:
                pass
        
        # SQLite database
        if self.use_sqlite:
            self.db_path = self.log_dir / "evaluation_runs.db"
            self._init_db()
        
        # JSONL log file
        if self.use_jsonl:
            self.jsonl_path = self.log_dir / "evaluation_runs.jsonl"
    
    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                run_id TEXT UNIQUE NOT NULL,
                evaluation_type TEXT,
                method TEXT,
                test_set_path TEXT,
                num_queries INTEGER,
                metrics TEXT,  -- JSON string
                config TEXT,   -- JSON string
                notes TEXT,
                schema_version INTEGER DEFAULT 1,
                checksum TEXT,  -- Optional checksum for integrity
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add schema_version column if it doesn't exist (migration)
        try:
            cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN schema_version INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        
        # Add checksum column if it doesn't exist (migration)
        try:
            cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN checksum TEXT")
        except sqlite3.OperationalError:
            pass
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON evaluation_runs(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_evaluation_type ON evaluation_runs(evaluation_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_method ON evaluation_runs(method)
        """)
        
        conn.commit()
        conn.close()
    
    def _validate_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Validate record using Pydantic if available."""
        # Add schema version if not present
        if "schema_version" not in record:
            record["schema_version"] = SCHEMA_VERSION
        
        if self.validate and HAS_PYDANTIC:
            try:
                validated = EvaluationRunRecord(**record)
                return validated.model_dump()
            except Exception as e:
                # Log warning but don't fail
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Validation failed for evaluation record: {e}")
                # Return original record if validation fails
                return record
        return record
    
    def _validate_on_read(self, record: dict[str, Any]) -> dict[str, Any]:
        """Validate record when reading from files."""
        if self.validate_on_read and HAS_PYDANTIC:
            try:
                # Add schema_version if missing (backward compatibility)
                if "schema_version" not in record:
                    record["schema_version"] = SCHEMA_VERSION
                
                validated = EvaluationRunRecord(**record)
                return validated.model_dump()
            except Exception as e:
                # Log warning but return record (don't fail on read)
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Read validation failed: {e}")
                return record
        return record
    
    def log_evaluation(
        self,
        evaluation_type: str,
        method: str,
        metrics: dict[str, Any],
        test_set_path: str | Path | None = None,
        num_queries: int | None = None,
        config: dict[str, Any] | None = None,
        notes: str | None = None,
        run_id: str | None = None,
    ) -> str:
        """
        Log an evaluation run.
        
        Args:
            evaluation_type: Type of evaluation (e.g., "precision_at_k", "ndcg", "fusion_comparison")
            method: Method evaluated (e.g., "embedding", "fusion_rrf", "fusion_weighted")
            metrics: Dictionary of metrics (e.g., {"p_at_k": 0.1763, "mrr": 0.3950})
            test_set_path: Path to test set used
            num_queries: Number of queries evaluated
            config: Configuration used (weights, aggregator, etc.)
            notes: Optional notes about the run
            run_id: Optional custom run ID (auto-generated if not provided)
        
        Returns:
            Run ID for this evaluation
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        if run_id is None:
            run_id = f"{evaluation_type}_{method}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "timestamp": timestamp,
            "evaluation_type": evaluation_type,
            "method": method,
            "test_set_path": str(test_set_path) if test_set_path else None,
            "num_queries": num_queries,
            "metrics": metrics,
            "config": config or {},
            "notes": notes,
        }
        
        # Validate record
        record = self._validate_record(record)
        
        # SQLite logging
        if self.use_sqlite:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO evaluation_runs 
                    (timestamp, run_id, evaluation_type, method, test_set_path, num_queries, metrics, config, notes, schema_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["timestamp"],
                    record["run_id"],
                    record["evaluation_type"],
                    record["method"],
                    record["test_set_path"],
                    record["num_queries"],
                    json.dumps(record["metrics"]),
                    json.dumps(record["config"]),
                    record["notes"],
                    record.get("schema_version", SCHEMA_VERSION),
                ))
                conn.commit()
            except sqlite3.IntegrityError:
                # Duplicate run_id - skip
                conn.rollback()
            finally:
                conn.close()
        
        # JSONL logging (append-only)
        if self.use_jsonl:
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        
        # JSON logging (one file per run) - OPTIONAL
        if self.use_json:
            json_path = self.log_dir / f"{run_id}.json"
            with open(json_path, "w") as f:
                json.dump(record, f, indent=2)
        
        # Optional: Write to EXPERIMENT_LOG
        if self.write_to_experiment_log and self.experiment_log_path:
            try:
                experiment_record = {
                    "experiment_type": "evaluation",
                    "evaluation_type": evaluation_type,
                    "method": method,
                    "metrics": metrics,
                    "timestamp": timestamp,
                    "run_id": run_id,
                    "test_set_path": str(test_set_path) if test_set_path else None,
                    "num_queries": num_queries,
                    "config": config or {},
                    "notes": notes,
                    "schema_version": SCHEMA_VERSION,
                }
                with open(self.experiment_log_path, "a") as f:
                    f.write(json.dumps(experiment_record) + "\n")
            except Exception:
                # Don't fail if experiment log write fails
                pass
        
        # Optional: Bridge to EvaluationRegistry
        if self.bridge_to_registry and self.registry:
            try:
                # Extract model info from config if available
                model_type = config.get("model_type", "unknown") if config else "unknown"
                model_version = config.get("model_version", run_id) if config else run_id
                model_path = config.get("model_path", "unknown") if config else "unknown"
                
                # Convert metrics to evaluation_results format
                evaluation_results = {
                    "metrics": metrics,
                    "num_queries": num_queries,
                    "config": config or {},
                }
                
                self.registry.record_evaluation(
                    model_type=model_type,
                    model_version=model_version,
                    model_path=model_path,
                    evaluation_results=evaluation_results,
                    test_set_path=test_set_path,
                    metadata={"run_id": run_id, "evaluation_type": evaluation_type, "method": method},
                    is_production=False,
                )
            except Exception:
                # Don't fail if registry write fails
                pass
        
        return run_id
    
    def get_recent_runs(
        self,
        limit: int = 10,
        evaluation_type: str | None = None,
        method: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get recent evaluation runs.
        
        Args:
            limit: Maximum number of runs to return
            evaluation_type: Filter by evaluation type
            method: Filter by method
        
        Returns:
            List of evaluation run records (validated if validate_on_read enabled)
        """
        if not self.use_sqlite:
            # Fallback to JSONL
            runs = []
            if self.jsonl_path.exists():
                with open(self.jsonl_path) as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            if self.validate_on_read:
                                record = self._validate_on_read(record)
                            runs.append(record)
            
            # Filter and sort
            if evaluation_type:
                runs = [r for r in runs if r.get("evaluation_type") == evaluation_type]
            if method:
                runs = [r for r in runs if r.get("method") == method]
            
            runs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return runs[:limit]
        
        # SQLite query
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM evaluation_runs WHERE 1=1"
        params = []
        
        if evaluation_type:
            query += " AND evaluation_type = ?"
            params.append(evaluation_type)
        
        if method:
            query += " AND method = ?"
            params.append(method)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        runs = []
        for row in rows:
            run = dict(row)
            run["metrics"] = json.loads(run["metrics"])
            run["config"] = json.loads(run["config"])
            if self.validate_on_read:
                run = self._validate_on_read(run)
            runs.append(run)
        
        conn.close()
        return runs
    
    def get_run_by_id(self, run_id: str) -> dict[str, Any] | None:
        """Get a specific evaluation run by ID (with read validation)."""
        if self.use_sqlite:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM evaluation_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            
            if row:
                run = dict(row)
                run["metrics"] = json.loads(run["metrics"])
                run["config"] = json.loads(run["config"])
                if self.validate_on_read:
                    run = self._validate_on_read(run)
                conn.close()
                return run
            
            conn.close()
            return None
        
        # Fallback to JSONL
        if self.jsonl_path.exists():
            with open(self.jsonl_path) as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if record.get("run_id") == run_id:
                            if self.validate_on_read:
                                record = self._validate_on_read(record)
                            return record
        
        return None
    
    def query_runs(
        self,
        evaluation_type: str | None = None,
        method: str | None = None,
        min_p_at_k: float | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query evaluation runs with filters.
        
        Args:
            evaluation_type: Filter by evaluation type
            method: Filter by method
            min_p_at_k: Minimum P@K value
            date_from: Start date (ISO format)
            date_to: End date (ISO format)
        
        Returns:
            List of matching evaluation runs (validated if validate_on_read enabled)
        """
        if not self.use_sqlite:
            # Fallback: load all and filter
            runs = []
            if self.jsonl_path.exists():
                with open(self.jsonl_path) as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            if self.validate_on_read:
                                record = self._validate_on_read(record)
                            runs.append(record)
            
            # Apply filters
            filtered = []
            for run in runs:
                if evaluation_type and run.get("evaluation_type") != evaluation_type:
                    continue
                if method and run.get("method") != method:
                    continue
                if min_p_at_k is not None:
                    metrics = run.get("metrics", {})
                    p_at_k = metrics.get("p_at_k") or metrics.get("p_at_10") or 0.0
                    if p_at_k < min_p_at_k:
                        continue
                if date_from and run.get("timestamp", "") < date_from:
                    continue
                if date_to and run.get("timestamp", "") > date_to:
                    continue
                filtered.append(run)
            
            return filtered
        
        # SQLite query
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM evaluation_runs WHERE 1=1"
        params = []
        
        if evaluation_type:
            query += " AND evaluation_type = ?"
            params.append(evaluation_type)
        
        if method:
            query += " AND method = ?"
            params.append(method)
        
        if date_from:
            query += " AND timestamp >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND timestamp <= ?"
            params.append(date_to)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        runs = []
        for row in rows:
            run = dict(row)
            run["metrics"] = json.loads(run["metrics"])
            run["config"] = json.loads(run["config"])
            
            # Filter by min_p_at_k (post-query since it's in JSON)
            if min_p_at_k is not None:
                metrics = run["metrics"]
                p_at_k = metrics.get("p_at_k") or metrics.get("p_at_10") or 0.0
                if p_at_k < min_p_at_k:
                    continue
            
            if self.validate_on_read:
                run = self._validate_on_read(run)
            runs.append(run)
        
        conn.close()
        return runs


# Global logger instance
_logger: EvaluationLogger | None = None


def get_logger() -> EvaluationLogger:
    """Get or create global evaluation logger."""
    global _logger
    if _logger is None:
        _logger = EvaluationLogger()
    return _logger


def log_evaluation_run(
    evaluation_type: str,
    method: str,
    metrics: dict[str, Any],
    **kwargs: Any,
) -> str:
    """
    Convenience function to log an evaluation run.
    
    Usage:
        run_id = log_evaluation_run(
            "precision_at_k",
            "fusion_rrf",
            {"p_at_k": 0.1763, "mrr": 0.3950},
            num_queries=939,
            config={"weights": {"embed": 0.75, "jaccard": 0.25}},
            notes="Grid search optimal weights"
        )
    """
    logger = get_logger()
    return logger.log_evaluation(
        evaluation_type=evaluation_type,
        method=method,
        metrics=metrics,
        **kwargs,
    )
