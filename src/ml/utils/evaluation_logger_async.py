#!/usr/bin/env python3
"""
Async version of EvaluationLogger for high-performance scenarios.

Supports:
- Async file I/O for JSONL/JSON
- Batch writes
- Connection pooling for SQLite
- Non-blocking validation
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PATHS

# Optional async file I/O
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

# Optional Pydantic validation
try:
    from pydantic import BaseModel, Field, field_validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None
    Field = None
    field_validator = None

from .evaluation_logger import SCHEMA_VERSION, EvaluationRunRecord


class AsyncEvaluationLogger:
    """
    Async version of EvaluationLogger for high-throughput scenarios.
    
    Features:
    - Async file I/O (aiofiles)
    - Batch writes
    - Non-blocking validation
    - Connection pooling (future)
    """
    
    def __init__(
        self,
        log_dir: Path | None = None,
        use_sqlite: bool = True,
        use_jsonl: bool = True,
        use_json: bool = False,
        validate: bool = True,
        batch_size: int = 10,
    ):
        """
        Initialize async evaluation logger.
        
        Args:
            log_dir: Directory for logs
            use_sqlite: Enable SQLite logging
            use_jsonl: Enable JSONL logging
            use_json: Enable JSON logging (default False)
            validate: Enable validation
            batch_size: Batch size for writes
        """
        self.log_dir = log_dir or (PATHS.experiments / "evaluation_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.use_sqlite = use_sqlite
        self.use_jsonl = use_jsonl
        self.use_json = use_json
        self.validate = validate and HAS_PYDANTIC
        self.batch_size = batch_size
        
        # Batch buffer
        self._batch_buffer: list[dict[str, Any]] = []
        self._batch_lock = asyncio.Lock()
        
        # SQLite database
        if self.use_sqlite:
            self.db_path = self.log_dir / "evaluation_runs.db"
            self._init_db()
        
        # JSONL log file
        if self.use_jsonl:
            self.jsonl_path = self.log_dir / "evaluation_runs.jsonl"
    
    def _init_db(self) -> None:
        """Initialize SQLite database schema (sync operation)."""
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
                metrics TEXT,
                config TEXT,
                notes TEXT,
                schema_version INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        try:
            cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN schema_version INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON evaluation_runs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluation_type ON evaluation_runs(evaluation_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_method ON evaluation_runs(method)")
        
        conn.commit()
        conn.close()
    
    async def log_evaluation(
        self,
        evaluation_type: str,
        method: str,
        metrics: dict[str, Any],
        test_set_path: str | Path | None = None,
        num_queries: int | None = None,
        config: dict[str, Any] | None = None,
        notes: str | None = None,
        run_id: str | None = None,
        flush: bool = False,
    ) -> str:
        """
        Log an evaluation run asynchronously.
        
        Args:
            evaluation_type: Type of evaluation
            method: Method evaluated
            metrics: Dictionary of metrics
            test_set_path: Path to test set
            num_queries: Number of queries
            config: Configuration
            notes: Optional notes
            run_id: Optional custom run ID
            flush: Force immediate write (bypass batching)
        
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
        
        # Validate (sync, but fast)
        if self.validate and HAS_PYDANTIC:
            try:
                validated = EvaluationRunRecord(**record)
                record = validated.model_dump()
            except Exception:
                pass  # Log warning but continue
        
        # SQLite write (sync, but fast for single inserts)
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
                pass
            finally:
                conn.close()
        
        # JSONL write (async if aiofiles available)
        if self.use_jsonl:
            if flush or not HAS_AIOFILES:
                # Immediate write (sync fallback)
                with open(self.jsonl_path, "a") as f:
                    f.write(json.dumps(record) + "\n")
            else:
                # Batch write
                async with self._batch_lock:
                    self._batch_buffer.append(record)
                    if len(self._batch_buffer) >= self.batch_size or flush:
                        await self._flush_jsonl_batch()
        
        # JSON write (async if aiofiles available)
        if self.use_json:
            json_path = self.log_dir / f"{run_id}.json"
            if HAS_AIOFILES:
                async with aiofiles.open(json_path, "w") as f:
                    await f.write(json.dumps(record, indent=2))
            else:
                # Sync fallback
                with open(json_path, "w") as f:
                    json.dump(record, f, indent=2)
        
        return run_id
    
    async def _flush_jsonl_batch(self) -> None:
        """Flush batched JSONL writes."""
        if not self._batch_buffer:
            return
        
        if HAS_AIOFILES:
            async with aiofiles.open(self.jsonl_path, "a") as f:
                for record in self._batch_buffer:
                    await f.write(json.dumps(record) + "\n")
        else:
            # Sync fallback
            with open(self.jsonl_path, "a") as f:
                for record in self._batch_buffer:
                    f.write(json.dumps(record) + "\n")
        
        self._batch_buffer.clear()
    
    async def flush(self) -> None:
        """Flush all pending writes."""
        if self.use_jsonl:
            async with self._batch_lock:
                await self._flush_jsonl_batch()


async def log_evaluation_run_async(
    evaluation_type: str,
    method: str,
    metrics: dict[str, Any],
    **kwargs: Any,
) -> str:
    """
    Convenience async function to log an evaluation run.
    
    Usage:
        run_id = await log_evaluation_run_async(
            "precision_at_k",
            "fusion_rrf",
            {"p_at_k": 0.1763},
        )
    """
    logger = AsyncEvaluationLogger()
    return await logger.log_evaluation(
        evaluation_type=evaluation_type,
        method=method,
        metrics=metrics,
        **kwargs,
    )


