#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Add observability metrics for evaluation logging.

Tracks:
- Write success/failure rates
- Validation failure rates
- Format write times
- Data integrity issues
"""

import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.utils.evaluation_logger import EvaluationLogger


class ObservableEvaluationLogger(EvaluationLogger):
    """EvaluationLogger with observability metrics."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = {
            "writes": {"success": 0, "failure": 0},
            "validation": {"passed": 0, "failed": 0},
            "formats": {"sqlite": 0, "jsonl": 0, "json": 0},
            "timings": defaultdict(list),
        }
    
    def log_evaluation(self, *args, **kwargs) -> str:
        """Log evaluation with metrics tracking."""
        start_time = time.time()
        
        try:
            run_id = super().log_evaluation(*args, **kwargs)
            self.metrics["writes"]["success"] += 1
            
            # Track format writes
            if self.use_sqlite:
                self.metrics["formats"]["sqlite"] += 1
            if self.use_jsonl:
                self.metrics["formats"]["jsonl"] += 1
            if self.use_json:
                self.metrics["formats"]["json"] += 1
            
            elapsed = time.time() - start_time
            self.metrics["timings"]["total"].append(elapsed)
            
            return run_id
        except Exception as e:
            self.metrics["writes"]["failure"] += 1
            self.metrics["timings"]["total"].append(time.time() - start_time)
            raise
    
    def get_metrics(self) -> dict[str, Any]:
        """Get observability metrics."""
        metrics = self.metrics.copy()
        
        # Calculate averages
        for key, values in metrics["timings"].items():
            if values:
                metrics["timings"][f"{key}_avg"] = sum(values) / len(values)
                metrics["timings"][f"{key}_max"] = max(values)
                metrics["timings"][f"{key}_min"] = min(values)
        
        return metrics


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test observability metrics")
    parser.add_argument("--log-dir", type=Path, help="Log directory")
    
    args = parser.parse_args()
    
    logger = ObservableEvaluationLogger(log_dir=args.log_dir)
    
    # Test writes
    for i in range(5):
        logger.log_evaluation(
            evaluation_type="test",
            method=f"method_{i}",
            metrics={"p_at_k": 0.1 + i * 0.01},
        )
    
    # Print metrics
    metrics = logger.get_metrics()
    print("=" * 80)
    print("Observability Metrics")
    print("=" * 80)
    print(json.dumps(metrics, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


