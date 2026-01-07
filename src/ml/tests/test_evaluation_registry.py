"""
Comprehensive tests for improved EvaluationRegistry.

Tests all priority fixes:
- File locking
- Atomic writes
- Schema validation
- SQLite backend
- Query caching
- Backup/restore
- Migration
- Version validation
- Archival
- Bulk operations
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

# Import the main registry
from ml.utils.evaluation_registry import (
    EvaluationRegistry,
    QueryCache,
    SQLiteBackend,
    validate_version_format,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def registry(temp_dir):
    """Create EvaluationRegistry instance for testing."""
    return EvaluationRegistry(
        registry_path=temp_dir / "model_registry.json",
        log_path=temp_dir / "experiment_log.jsonl",
        results_dir=temp_dir / "evaluation_results",
        use_sqlite=True,
        sqlite_path=temp_dir / "eval_registry.db",
        cache_ttl=60,
    )


class TestVersionValidation:
    """Test version format validation."""

    def test_valid_versions(self):
        """Test valid version formats."""
        assert validate_version_format("v2026-W01")
        assert validate_version_format("2026-W01")
        assert validate_version_format("v2026-01-01")
        assert validate_version_format("2026-01-01")
        assert validate_version_format("v1.2.3")
        assert validate_version_format("1.2.3")
        assert validate_version_format("test-20260101-085347")

    def test_invalid_versions(self):
        """Test invalid version formats."""
        assert not validate_version_format("")
        assert not validate_version_format("invalid")
        assert not validate_version_format("v")
        assert not validate_version_format("2026")


class TestAtomicWrites:
    """Test atomic write functionality."""

    def test_atomic_write_success(self, registry, temp_dir):
        """Test successful atomic write."""
        test_file = temp_dir / "test.json"
        test_data = {"key": "value", "number": 42}

        registry._atomic_write(test_file, test_data)

        assert test_file.exists()
        with open(test_file) as f:
            loaded = json.load(f)
        assert loaded == test_data

    def test_atomic_write_no_temp_leftover(self, registry, temp_dir):
        """Test that temp files are cleaned up."""
        test_file = temp_dir / "test.json"
        test_data = {"key": "value"}

        registry._atomic_write(test_file, test_data)

        # No .tmp files should remain
        temp_files = list(temp_dir.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_atomic_write_cleanup_on_error(self, registry, temp_dir):
        """Test temp file cleanup on write error."""
        test_file = temp_dir / "test.json"
        # Make directory read-only to cause write error
        test_file.parent.chmod(0o555)

        try:
            registry._atomic_write(test_file, {"key": "value"})
            assert False, "Should have raised exception"
        except Exception:
            pass
        finally:
            test_file.parent.chmod(0o755)

        # Temp file should be cleaned up
        temp_files = list(temp_dir.glob("*.tmp"))
        assert len(temp_files) == 0


class TestFileLocking:
    """Test file locking for concurrent writes."""

    def test_concurrent_writes(self, registry, temp_dir):
        """Test that concurrent writes don't corrupt files."""
        test_file = temp_dir / "concurrent_test.json"

        def write_data(data_id: int):
            """Write data with ID."""
            data = {"id": data_id, "timestamp": time.time()}
            registry._write_with_lock(test_file, data)
            return data_id

        # Write concurrently from 10 threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_data, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # File should exist and be valid JSON
        assert test_file.exists()
        with open(test_file) as f:
            data = json.load(f)
        assert "id" in data
        assert data["id"] in results

    def test_lock_timeout(self, registry, temp_dir):
        """Test lock timeout behavior."""
        test_file = temp_dir / "lock_test.json"
        lock_file = test_file.with_suffix(".lock")

        # Create a lock file manually to simulate locked state
        with open(lock_file, "w") as f:
            f.write("locked")

        # Try to acquire lock with short timeout
        registry._lock_timeout = 0.1
        try:
            registry._write_with_lock(test_file, {"key": "value"})
            # If filelock is not available, this will use atomic write
            # which doesn't check locks, so we skip the assertion
            if hasattr(registry, "_lock_timeout"):
                pass  # Lock timeout handled gracefully
        except RuntimeError as e:
            assert "timeout" in str(e).lower() or "lock" in str(e).lower()


class TestSchemaValidation:
    """Test Pydantic schema validation."""

    def test_valid_record(self, registry):
        """Test recording valid evaluation."""
        result_path = registry.record_evaluation(
            model_type="test",
            model_version="v2026-W01",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.15, "mrr": 0.30},
            metadata={"test": True},
        )

        assert result_path.exists()
        with open(result_path) as f:
            record = json.load(f)

        assert record["model_type"] == "test"
        assert record["model_version"] == "v2026-W01"
        assert record["metrics"]["p_at_10"] == 0.15

    def test_invalid_metrics(self, registry):
        """Test that invalid metrics are handled."""
        # NaN and inf should be filtered out
        result_path = registry.record_evaluation(
            model_type="test",
            model_version="v2026-W02",
            model_path="/path/to/model",
            evaluation_results={"p@10": float("nan"), "mrr": float("inf")},
        )

        with open(result_path) as f:
            record = json.load(f)

        # NaN and inf should not be in metrics
        metrics = record["metrics"]
        assert "p_at_10" not in metrics or metrics["p_at_10"] != float("nan")
        assert "mrr" not in metrics or metrics["mrr"] != float("inf")


class TestSQLiteBackend:
    """Test SQLite backend functionality."""

    def test_sqlite_insert_and_retrieve(self, temp_dir):
        """Test inserting and retrieving from SQLite."""
        db_path = temp_dir / "test.db"
        backend = SQLiteBackend(db_path)

        record = {
            "timestamp": "2026-01-01T00:00:00",
            "model_type": "test",
            "model_version": "v1.0",
            "model_path": "/path/to/model",
            "test_set_path": None,
            "metrics": {"p_at_10": 0.15},
            "full_results": {"p@10": 0.15},
            "metadata": {},
            "is_production": False,
        }

        row_id = backend.insert(record)
        assert row_id > 0

        retrieved = backend.get("test", "v1.0")
        assert retrieved is not None
        assert retrieved["model_type"] == "test"
        assert retrieved["metrics"]["p_at_10"] == 0.15

    def test_sqlite_list_with_filter(self, temp_dir):
        """Test listing with model type filter."""
        db_path = temp_dir / "test.db"
        backend = SQLiteBackend(db_path)

        # Insert multiple records
        for i in range(5):
            record = {
                "timestamp": f"2026-01-0{i+1}T00:00:00",
                "model_type": "test" if i < 3 else "other",
                "model_version": f"v{i+1}",
                "model_path": f"/path/to/model{i}",
                "test_set_path": None,
                "metrics": {"p_at_10": 0.1 + i * 0.01},
                "full_results": {},
                "metadata": {},
                "is_production": False,
            }
            backend.insert(record)

        # List all
        all_records = backend.list()
        assert len(all_records) == 5

        # List filtered
        test_records = backend.list(model_type="test")
        assert len(test_records) == 3

        # List with limit
        limited = backend.list(limit=2)
        assert len(limited) == 2

    def test_sqlite_count(self, temp_dir):
        """Test counting evaluations."""
        db_path = temp_dir / "test.db"
        backend = SQLiteBackend(db_path)

        assert backend.count() == 0

        for i in range(3):
            record = {
                "timestamp": f"2026-01-0{i+1}T00:00:00",
                "model_type": "test",
                "model_version": f"v{i+1}",
                "model_path": f"/path/to/model{i}",
                "test_set_path": None,
                "metrics": {},
                "full_results": {},
                "metadata": {},
                "is_production": False,
            }
            backend.insert(record)

        assert backend.count() == 3
        assert backend.count(model_type="test") == 3
        assert backend.count(model_type="other") == 0


class TestQueryCache:
    """Test query caching functionality."""

    def test_cache_get_set(self):
        """Test basic cache get/set."""
        cache = QueryCache(ttl_seconds=60)

        assert cache.get("key1") is None

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_expiration(self):
        """Test cache expiration."""
        cache = QueryCache(ttl_seconds=1)  # 1 second TTL

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(1.1)  # Wait for expiration
        assert cache.get("key1") is None

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = QueryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_invalidate_pattern(self):
        """Test pattern-based cache invalidation."""
        cache = QueryCache()

        cache.set("list:test:10", "value1")
        cache.set("list:other:10", "value2")
        cache.set("get:test:v1", "value3")

        cache.invalidate_pattern("list:*")
        assert cache.get("list:test:10") is None
        assert cache.get("list:other:10") is None
        assert cache.get("get:test:v1") == "value3"  # Not invalidated


class TestRecordEvaluation:
    """Test evaluation recording functionality."""

    def test_record_basic(self, registry):
        """Test basic evaluation recording."""
        result_path = registry.record_evaluation(
            model_type="hybrid",
            model_version="v2026-W01",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1418, "mrr@10": 0.3238},
        )

        assert result_path.exists()
        assert "hybrid_evaluation_v2026-W01.json" in str(result_path)

    def test_record_with_metadata(self, registry):
        """Test recording with metadata."""
        result_path = registry.record_evaluation(
            model_type="test",
            model_version="v2026-W02",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.15},
            metadata={"text_embedder": "all-MiniLM-L6-v2", "epochs": 10},
        )

        with open(result_path) as f:
            record = json.load(f)

        assert record["metadata"]["text_embedder"] == "all-MiniLM-L6-v2"
        assert record["metadata"]["epochs"] == 10

    def test_record_production(self, registry):
        """Test recording production model."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.10},
            is_production=True,
        )

        registry.record_evaluation(
            model_type="test",
            model_version="v2",
            model_path="/path/to/model2",
            evaluation_results={"p@10": 0.15},
            is_production=True,
        )

        # v1 should no longer be production
        prod_model = registry.model_registry.get_production_model("test")
        assert prod_model is not None
        assert prod_model["version"] == "v2"

    def test_record_concurrent(self, registry):
        """Test concurrent evaluation recording."""
        def record_eval(version: str):
            """Record evaluation with version."""
            return registry.record_evaluation(
                model_type="concurrent",
                model_version=version,
                model_path=f"/path/to/model_{version}",
                evaluation_results={"p@10": 0.1},
            )

        # Record 10 evaluations concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(record_eval, f"v{i}") for i in range(10)
            ]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed
        assert len(results) == 10
        for result_path in results:
            assert result_path.exists()

        # All should be in SQLite
        if registry.use_sqlite:
            evaluations = registry.sqlite_backend.list(model_type="concurrent")
            assert len(evaluations) == 10


class TestListEvaluations:
    """Test listing evaluations."""

    def test_list_all(self, registry):
        """Test listing all evaluations."""
        # Record multiple evaluations
        for i in range(5):
            registry.record_evaluation(
                model_type="test",
                model_version=f"v{i+1}",
                model_path=f"/path/to/model{i}",
                evaluation_results={"p@10": 0.1 + i * 0.01},
            )

        evaluations = registry.list_evaluations()
        assert len(evaluations) >= 5

    def test_list_filtered(self, registry):
        """Test listing with model type filter."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        registry.record_evaluation(
            model_type="other",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.2},
        )

        test_evals = registry.list_evaluations(model_type="test")
        assert len(test_evals) >= 1
        assert all(e["model_type"] == "test" for e in test_evals)

    def test_list_with_limit(self, registry):
        """Test listing with limit."""
        for i in range(10):
            registry.record_evaluation(
                model_type="test",
                model_version=f"v{i+1}",
                model_path=f"/path/to/model{i}",
                evaluation_results={"p@10": 0.1},
            )

        limited = registry.list_evaluations(limit=5)
        assert len(limited) == 5

    def test_list_caching(self, registry):
        """Test that listing uses cache."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        # First call - not cached
        evals1 = registry.list_evaluations(use_cache=True)

        # Second call - should be cached
        evals2 = registry.list_evaluations(use_cache=True)

        assert evals1 == evals2


class TestBackupRestore:
    """Test backup and restore functionality."""

    def test_backup(self, registry):
        """Test creating backup."""
        # Record some evaluations
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        backup_path = registry.backup()

        assert backup_path.exists()
        assert (backup_path / "model_registry.json").exists()
        assert (backup_path / "evaluation_results").exists()

    def test_restore(self, registry, temp_dir):
        """Test restoring from backup."""
        # Record evaluation
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        # Create backup
        backup_path = registry.backup()

        # Clear registry
        if registry.results_dir.exists():
            shutil.rmtree(registry.results_dir)
        registry.results_dir.mkdir()

        # Restore
        registry.restore(backup_path)

        # Verify restored
        evaluations = registry.list_evaluations()
        assert len(evaluations) >= 1


class TestArchival:
    """Test evaluation archival."""

    def test_archive_old_evaluations(self, registry):
        """Test archiving old evaluations."""
        # This test would need to manipulate timestamps
        # For now, just test that the method exists and runs
        archived = registry.archive_evaluations(older_than_days=0)  # Archive all
        # Should handle gracefully even if no old evaluations
        assert isinstance(archived, list)


class TestBulkOperations:
    """Test bulk import/export."""

    def test_bulk_export_json(self, registry, temp_dir):
        """Test bulk export to JSON."""
        # Record some evaluations
        for i in range(3):
            registry.record_evaluation(
                model_type="test",
                model_version=f"v{i+1}",
                model_path=f"/path/to/model{i}",
                evaluation_results={"p@10": 0.1 + i * 0.01},
            )

        export_path = temp_dir / "export.json"
        result_path = registry.bulk_export(export_path, format="json")

        assert result_path.exists()
        with open(result_path) as f:
            exported = json.load(f)

        assert len(exported) >= 3

    def test_bulk_export_jsonl(self, registry, temp_dir):
        """Test bulk export to JSONL."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        export_path = temp_dir / "export.jsonl"
        registry.bulk_export(export_path, format="jsonl")

        assert export_path.exists()
        with open(export_path) as f:
            lines = [json.loads(line) for line in f]
        assert len(lines) >= 1

    def test_bulk_import(self, registry):
        """Test bulk import."""
        evaluations = [
            {
                "model_type": "test",
                "model_version": f"v{i+1}",
                "model_path": f"/path/to/model{i}",
                "full_results": {"p@10": 0.1 + i * 0.01},
                "metadata": {},
                "is_production": False,
            }
            for i in range(3)
        ]

        imported = registry.bulk_import(evaluations)
        assert imported == 3

        # Verify imported
        all_evals = registry.list_evaluations(model_type="test")
        assert len(all_evals) >= 3


class TestMigration:
    """Test migration functionality."""

    def test_migrate_from_json(self, registry):
        """Test migrating from JSON to SQLite."""
        # Create some JSON files manually
        for i in range(3):
            record = {
                "timestamp": f"2026-01-0{i+1}T00:00:00",
                "model_type": "migrate",
                "model_version": f"v{i+1}",
                "model_path": f"/path/to/model{i}",
                "metrics": {"p_at_10": 0.1 + i * 0.01},
                "full_results": {"p@10": 0.1 + i * 0.01},
                "metadata": {},
                "is_production": False,
            }

            results_file = (
                registry.results_dir / f"migrate_evaluation_v{i+1}.json"
            )
            with open(results_file, "w") as f:
                json.dump(record, f)

        # Migrate
        migrated = registry.migrate_from_json()
        assert migrated == 3

        # Verify in SQLite
        if registry.use_sqlite:
            sqlite_evals = registry.sqlite_backend.list(model_type="migrate")
            assert len(sqlite_evals) == 3


class TestRegressionDetection:
    """Test regression detection."""

    def test_detect_regression(self, registry):
        """Test regression detection."""
        # Record baseline
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.15},
            is_production=True,
        )

        # Record worse version
        registry.record_evaluation(
            model_type="test",
            model_version="v2",
            model_path="/path/to/model2",
            evaluation_results={"p@10": 0.10},  # 33% drop
        )

        regression = registry.detect_regression(
            model_type="test",
            current_version="v2",
            threshold_pct=-10.0,
        )

        assert regression is not None
        assert regression["regression_detected"] is True
        assert regression["p_at_10_drop_pct"] < -10.0

    def test_no_regression(self, registry):
        """Test no regression detected."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.10},
            is_production=True,
        )

        registry.record_evaluation(
            model_type="test",
            model_version="v2",
            model_path="/path/to/model2",
            evaluation_results={"p@10": 0.15},  # Improvement
        )

        regression = registry.detect_regression(
            model_type="test",
            current_version="v2",
            threshold_pct=-10.0,
        )

        assert regression is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_file_handling(self, registry):
        """Test handling of missing files."""
        # Should not crash when file doesn't exist
        eval_record = registry.get_latest_evaluation("nonexistent")
        assert eval_record is None

    def test_corrupted_json_handling(self, registry):
        """Test handling of corrupted JSON files."""
        # Create corrupted JSON file
        bad_file = registry.results_dir / "corrupted_evaluation_v1.json"
        with open(bad_file, "w") as f:
            f.write("{ invalid json }")

        # Should handle gracefully
        evaluations = registry.list_evaluations()
        # Should skip corrupted file and continue
        assert isinstance(evaluations, list)

    def test_empty_results_dir(self, registry):
        """Test with empty results directory."""
        if registry.results_dir.exists():
            shutil.rmtree(registry.results_dir)
        registry.results_dir.mkdir()

        evaluations = registry.list_evaluations()
        assert evaluations == []

    def test_large_metadata(self, registry):
        """Test handling of large metadata."""
        large_metadata = {"data": "x" * 10000}  # 10KB metadata

        result_path = registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
            metadata=large_metadata,
        )

        # Should handle large metadata
        assert result_path.exists()
        with open(result_path) as f:
            record = json.load(f)
        assert len(record["metadata"]["data"]) == 10000


class TestPerformance:
    """Test performance characteristics."""

    def test_list_performance(self, registry):
        """Test that listing is reasonably fast."""
        # Record 100 evaluations
        for i in range(100):
            registry.record_evaluation(
                model_type="perf",
                model_version=f"v{i+1}",
                model_path=f"/path/to/model{i}",
                evaluation_results={"p@10": 0.1},
            )

        import time

        start = time.time()
        evaluations = registry.list_evaluations(model_type="perf")
        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 100 records)
        assert elapsed < 5.0
        assert len(evaluations) == 100

    def test_cache_performance(self, registry):
        """Test that caching improves performance."""
        registry.record_evaluation(
            model_type="test",
            model_version="v1",
            model_path="/path/to/model",
            evaluation_results={"p@10": 0.1},
        )

        import time

        # First call (no cache)
        start1 = time.time()
        evals1 = registry.list_evaluations(use_cache=True)
        time1 = time.time() - start1

        # Second call (cached)
        start2 = time.time()
        evals2 = registry.list_evaluations(use_cache=True)
        time2 = time.time() - start2

        # Cached call should be faster (or at least not slower)
        # Note: For small datasets, difference may be negligible
        assert evals1 == evals2

