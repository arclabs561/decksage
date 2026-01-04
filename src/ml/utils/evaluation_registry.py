"""
Unified Evaluation Results Registry

Centralized system for recording and tracking evaluation results and model versions.
Integrates with ModelRegistry and provides structured logging for all evaluations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..model_registry import ModelRegistry
from ..utils.paths import PATHS

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


class EvaluationRegistry:
    """
    Unified registry for evaluation results and model versions.
    
    Integrates:
    - ModelRegistry: Model version tracking
    - StructuredLogger: JSON logging
    - Evaluation results: Versioned storage
    """
    
    def __init__(
        self,
        registry_path: Path | str | None = None,
        log_path: Path | str | None = None,
        results_dir: Path | str | None = None,
    ):
        """
        Initialize evaluation registry.
        
        Args:
            registry_path: Path to model registry JSON
            log_path: Path to structured log JSONL
            results_dir: Directory for versioned evaluation results
        """
        self.model_registry = ModelRegistry(registry_path)
        if HAS_STRUCTURED_LOGGING:
            # Use canonical experiment log path
            default_log_path = PATHS.experiments / "EXPERIMENT_LOG_CANONICAL.jsonl"
            self.structured_logger = StructuredLogger(log_path or default_log_path)
        else:
            self.structured_logger = None
        self.results_dir = Path(results_dir) if results_dir else PATHS.experiments / "evaluation_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
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
        
        Args:
            model_type: Type of model (e.g., "cooccurrence", "gnn", "hybrid")
            model_version: Version identifier (e.g., "v2026-W01", "v2026-01-01")
            model_path: Path to model file
            evaluation_results: Evaluation metrics and results
            test_set_path: Path to test set used
            metadata: Additional metadata (training params, etc.)
            is_production: Whether this is a production model
            save_versioned: Whether to save versioned results file
        
        Returns:
            Path to saved evaluation results file
        """
        timestamp = datetime.now().isoformat()
        
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
        
        # Save versioned results file
        if save_versioned:
            results_file = self.results_dir / f"{model_type}_evaluation_v{model_version}.json"
            with open(results_file, 'w') as f:
                json.dump(evaluation_record, f, indent=2)
            logger.info(f"Saved evaluation results: {results_file}")
        else:
            results_file = self.results_dir / f"{model_type}_evaluation_latest.json"
            with open(results_file, 'w') as f:
                json.dump(evaluation_record, f, indent=2)
            logger.info(f"Saved evaluation results: {results_file}")
        
        # Register model in registry
        self.model_registry.register_model(
            model_type=model_type,
            version=model_version,
            path=model_path,
            metrics=metrics,
            metadata={
                **(metadata or {}),
                "test_set_path": str(test_set_path) if test_set_path else None,
                "evaluation_timestamp": timestamp,
            },
            is_production=is_production,
        )
        
        # Log to structured log (if available)
        if self.structured_logger:
            self.structured_logger.log_event(
                event_type="evaluation",
                message=f"Evaluation recorded: {model_type} v{model_version}",
                level="info",
                model_type=model_type,
                model_version=model_version,
                metrics=metrics,
                results_file=str(results_file),
            )
        
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
        
        # Summary metrics (common in evaluate_hybrid_with_runctl.py)
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
        
        # Overall metrics (alternative format)
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
        
        # Downstream tasks (alternative format)
        if "downstream_tasks" in results:
            downstream = results["downstream_tasks"]
            if "completion_rate" in downstream:
                metrics["completion_rate"] = float(downstream["completion_rate"])
            if "substitution_accuracy" in downstream:
                metrics["substitution_accuracy"] = float(downstream["substitution_accuracy"])
        
        return metrics
    
    def compare_evaluations(
        self,
        model_type: str,
        version1: str,
        version2: str,
        metric: str = "p_at_10",
    ) -> dict[str, Any] | None:
        """
        Compare two evaluation versions.
        
        Returns:
            Comparison dict with deltas and regression detection
        """
        comparison = self.model_registry.compare_versions(
            model_type=model_type,
            version1=version1,
            version2=version2,
            metric=metric,
        )
        
        if comparison:
            # Load full evaluation results for detailed comparison
            results1_file = self.results_dir / f"{model_type}_evaluation_v{version1}.json"
            results2_file = self.results_dir / f"{model_type}_evaluation_v{version2}.json"
            
            if results1_file.exists() and results2_file.exists():
                with open(results1_file) as f:
                    results1 = json.load(f)
                with open(results2_file) as f:
                    results2 = json.load(f)
                
                comparison["full_results1"] = results1.get("full_results", {})
                comparison["full_results2"] = results2.get("full_results", {})
        
        return comparison
    
    def get_latest_evaluation(
        self,
        model_type: str,
        is_production: bool = False,
    ) -> dict[str, Any] | None:
        """
        Get latest evaluation results for a model type.
        
        Args:
            model_type: Type of model
            is_production: If True, return production model evaluation
        
        Returns:
            Evaluation record dict or None
        """
        if is_production:
            model = self.model_registry.get_production_model(model_type)
        else:
            versions = self.model_registry.list_versions(model_type)
            if not versions:
                return None
            model = versions[0]  # Most recent
        
        if not model:
            return None
        
        version = model["version"]
        results_file = self.results_dir / f"{model_type}_evaluation_v{version}.json"
        
        if results_file.exists():
            with open(results_file) as f:
                return json.load(f)
        
        return None
    
    def list_evaluations(
        self,
        model_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all evaluation records.
        
        Args:
            model_type: Filter by model type (optional)
            limit: Limit number of results (optional)
        
        Returns:
            List of evaluation records, sorted by timestamp (newest first)
        """
        evaluations = []
        
        # Also check for unversioned files (backwards compatibility)
        pattern = "*_evaluation*.json" if model_type is None else f"{model_type}_evaluation*.json"
        
        for results_file in sorted(self.results_dir.glob(pattern), reverse=True):
            try:
                with open(results_file) as f:
                    record = json.load(f)
                
                # Skip if not the right type
                if model_type is not None and record.get("model_type") != model_type:
                    continue
                
                # Ensure timestamp for sorting
                if "timestamp" not in record:
                    # Try to get from file mtime
                    try:
                        record["timestamp"] = datetime.fromtimestamp(results_file.stat().st_mtime).isoformat()
                    except (OSError, ValueError):
                        # Fallback to current time if file stat fails
                        record["timestamp"] = datetime.now().isoformat()
                
                evaluations.append(record)
            except Exception as e:
                logger.warning(f"Failed to load {results_file}: {e}")
        
        # Sort by timestamp (newest first)
        evaluations.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        if limit:
            evaluations = evaluations[:limit]
        
        return evaluations
    
    def detect_regression(
        self,
        model_type: str,
        current_version: str,
        previous_version: str | None = None,
        threshold_pct: float = -10.0,
    ) -> dict[str, Any] | None:
        """
        Detect performance regression between versions.
        
        Args:
            model_type: Type of model
            current_version: Current version to check
            previous_version: Previous version (if None, uses production)
            threshold_pct: Regression threshold (e.g., -10.0 for 10% drop)
        
        Returns:
            Regression report dict or None if no regression
        """
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
            
            # Log regression (if structured logger available)
            if self.structured_logger:
                self.structured_logger.log_event(
                    event_type="regression_detected",
                    message=f"Regression detected: {model_type} v{current_version}",
                    level="warning",
                    **regression_report,
                )
            
            return regression_report
        
        return None

