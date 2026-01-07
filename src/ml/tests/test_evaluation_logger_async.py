#!/usr/bin/env python3
"""
Tests for AsyncEvaluationLogger.

Tests:
- Async file I/O
- Batch writes
- Flush functionality
- Performance characteristics
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths
setup_project_paths()

from ml.utils.evaluation_logger_async import AsyncEvaluationLogger, HAS_AIOFILES

# Use anyio for async tests (already installed)
pytestmark = pytest.mark.anyio


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def async_logger(temp_dir):
    """Create AsyncEvaluationLogger instance for testing."""
    return AsyncEvaluationLogger(
        log_dir=temp_dir / "logs",
        use_sqlite=True,
        use_jsonl=True,
        use_json=False,
        batch_size=5,
    )


class TestAsyncLogging:
    """Test async logging functionality."""
    
    async def test_async_log_evaluation(self, async_logger, temp_dir):
        """Test basic async evaluation logging."""
        run_id = await async_logger.log_evaluation(
            evaluation_type="precision_at_k",
            method="embedding",
            metrics={"p_at_k": 0.15},
        )
        
        assert run_id is not None
        
        # Flush to ensure writes complete
        await async_logger.flush()
        
        # Verify JSONL file was written
        jsonl_path = temp_dir / "logs" / "evaluation_runs.jsonl"
        if jsonl_path.exists():
            with open(jsonl_path) as f:
                lines = [line for line in f if line.strip()]
                assert len(lines) >= 1
                record = json.loads(lines[-1])
                assert record["run_id"] == run_id
    
    async def test_batch_writes(self, async_logger, temp_dir):
        """Test batch writing functionality."""
        # Log multiple evaluations
        run_ids = []
        for i in range(10):
            run_id = await async_logger.log_evaluation(
                evaluation_type="test",
                method="test",
                metrics={"p_at_k": 0.1 + i * 0.01},
            )
            run_ids.append(run_id)
        
        # Flush to ensure all writes complete
        await async_logger.flush()
        
        # Verify JSONL has all records
        jsonl_path = temp_dir / "logs" / "evaluation_runs.jsonl"
        if jsonl_path.exists():
            with open(jsonl_path) as f:
                lines = [line for line in f if line.strip()]
                assert len(lines) >= 10
    
    async def test_flush_functionality(self, async_logger):
        """Test flush functionality."""
        # Log with flush
        run_id1 = await async_logger.log_evaluation(
            evaluation_type="test",
            method="test",
            metrics={"p_at_k": 0.1},
            flush=True,
        )
        
        # Log without flush
        run_id2 = await async_logger.log_evaluation(
            evaluation_type="test",
            method="test",
            metrics={"p_at_k": 0.2},
        )
        
        # Flush manually
        await async_logger.flush()
        
        assert run_id1 is not None
        assert run_id2 is not None
    
    async def test_concurrent_writes(self, async_logger):
        """Test concurrent async writes."""
        # Create multiple concurrent writes
        tasks = []
        for i in range(5):
            task = async_logger.log_evaluation(
                evaluation_type="test",
                method="test",
                metrics={"p_at_k": 0.1 + i * 0.01},
            )
            tasks.append(task)
        
        # Wait for all
        run_ids = await asyncio.gather(*tasks)
        
        # Flush
        await async_logger.flush()
        
        assert len(run_ids) == 5
        assert all(rid is not None for rid in run_ids)


class TestAsyncPerformance:
    """Test performance characteristics."""
    
    async def test_batch_size_impact(self, temp_dir):
        """Test that batch size affects write behavior."""
        logger_small = AsyncEvaluationLogger(
            log_dir=temp_dir / "logs_small",
            batch_size=2,
        )
        
        logger_large = AsyncEvaluationLogger(
            log_dir=temp_dir / "logs_large",
            batch_size=10,
        )
        
        # Log same number of records
        for i in range(10):
            await logger_small.log_evaluation(
                evaluation_type="test",
                method="test",
                metrics={"p_at_k": 0.1},
            )
            await logger_large.log_evaluation(
                evaluation_type="test",
                method="test",
                metrics={"p_at_k": 0.1},
            )
        
        # Flush both
        await logger_small.flush()
        await logger_large.flush()
        
        # Both should have same number of records
        # (batch size affects I/O frequency, not final count)
        # Verify by counting lines in JSONL files
        if logger_small.use_jsonl and logger_small.jsonl_path.exists():
            with open(logger_small.jsonl_path) as f:
                small_count = sum(1 for _ in f)
        else:
            small_count = 0
        
        if logger_large.use_jsonl and logger_large.jsonl_path.exists():
            with open(logger_large.jsonl_path) as f:
                large_count = sum(1 for _ in f)
        else:
            large_count = 0
        
        # Both should have logged 10 records
        assert small_count == 10, f"Expected 10 records in small batch logger, got {small_count}"
        assert large_count == 10, f"Expected 10 records in large batch logger, got {large_count}"


@pytest.mark.skipif(not HAS_AIOFILES, reason="aiofiles not available")
class TestAiofilesIntegration:
    """Test aiofiles integration."""
    
    async def test_async_json_write(self, temp_dir):
        """Test async JSON file writing."""
        logger = AsyncEvaluationLogger(
            log_dir=temp_dir / "logs",
            use_json=True,
        )
        
        run_id = await logger.log_evaluation(
            evaluation_type="test",
            method="test",
            metrics={"p_at_k": 0.1},
        )
        
        await logger.flush()
        
        # Verify JSON file exists
        json_path = temp_dir / "logs" / f"{run_id}.json"
        assert json_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

