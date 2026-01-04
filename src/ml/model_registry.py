"""Model registry for tracking versions and metadata."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils.paths import PATHS

try:
    from .utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class ModelRegistry:
    """Registry for tracking model versions and metadata."""
    
    def __init__(self, registry_path: Path | str | None = None):
        """
        Initialize model registry.
        
        Args:
            registry_path: Path to registry JSON file
        """
        self.registry_path = Path(registry_path) if registry_path else PATHS.experiments / "model_registry.json"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, Any] = self._load_registry()
    
    def _load_registry(self) -> dict[str, Any]:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load registry: {e}. Starting fresh.")
                return {"models": {}, "metadata": {"created_at": datetime.utcnow().isoformat() + "Z"}}
        else:
            return {"models": {}, "metadata": {"created_at": datetime.utcnow().isoformat() + "Z"}}
    
    def _save_registry(self) -> None:
        """Save registry to disk."""
        self._registry["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"
        with open(self.registry_path, 'w') as f:
            json.dump(self._registry, f, indent=2)
    
    def register_model(
        self,
        model_type: str,
        version: str,
        path: Path | str,
        metrics: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
        is_production: bool = False,
    ) -> None:
        """
        Register a model version.
        
        Args:
            model_type: Type of model (e.g., "gnn", "cooccurrence", "hybrid")
            version: Version tag (e.g., "2024-W52")
            path: Path to model file
            metrics: Performance metrics
            metadata: Additional metadata
            is_production: Whether this is the production version
        """
        model_key = f"{model_type}_{version}"
        
        entry = {
            "model_type": model_type,
            "version": version,
            "path": str(path),
            "registered_at": datetime.utcnow().isoformat() + "Z",
            "metrics": metrics or {},
            "metadata": metadata or {},
            "is_production": is_production,
        }
        
        self._registry["models"][model_key] = entry
        
        # If this is production, unmark other production versions of same type
        if is_production:
            for key, model in self._registry["models"].items():
                if (
                    model["model_type"] == model_type
                    and model["version"] != version
                    and model.get("is_production", False)
                ):
                    model["is_production"] = False
                    logger.info(f"Unmarked {key} as production (replaced by {model_key})")
        
        self._save_registry()
        logger.info(f"Registered model: {model_key}")
    
    def get_model(self, model_type: str, version: str) -> dict[str, Any] | None:
        """Get model entry by type and version."""
        model_key = f"{model_type}_{version}"
        return self._registry["models"].get(model_key)
    
    def get_production_model(self, model_type: str) -> dict[str, Any] | None:
        """Get current production model for a type."""
        for model in self._registry["models"].values():
            if model["model_type"] == model_type and model.get("is_production", False):
                return model
        return None
    
    def list_versions(self, model_type: str | None = None) -> list[dict[str, Any]]:
        """List all model versions, optionally filtered by type."""
        models = list(self._registry["models"].values())
        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        return sorted(models, key=lambda x: x["registered_at"], reverse=True)
    
    def compare_versions(
        self,
        model_type: str,
        version1: str,
        version2: str,
        metric: str = "p_at_10",
    ) -> dict[str, Any] | None:
        """
        Compare two model versions.
        
        Returns:
            Dict with comparison results, or None if either version not found
        """
        model1 = self.get_model(model_type, version1)
        model2 = self.get_model(model_type, version2)
        
        if not model1 or not model2:
            return None
        
        metrics1 = model1.get("metrics", {})
        metrics2 = model2.get("metrics", {})
        
        value1 = metrics1.get(metric)
        value2 = metrics2.get(metric)
        
        if value1 is None or value2 is None:
            return None
        
        delta = value2 - value1
        delta_pct = (delta / value1 * 100) if value1 != 0 else 0
        
        return {
            "model_type": model_type,
            "version1": version1,
            "version2": version2,
            "metric": metric,
            "value1": value1,
            "value2": value2,
            "delta": delta,
            "delta_pct": delta_pct,
            "improved": delta > 0,
        }
    
    def promote_to_production(
        self,
        model_type: str,
        version: str,
    ) -> bool:
        """
        Promote a model version to production.
        
        Returns:
            True if successful, False if model not found
        """
        model = self.get_model(model_type, version)
        if not model:
            logger.error(f"Model not found: {model_type}_{version}")
            return False
        
        # Unmark other production versions
        for key, m in self._registry["models"].items():
            if (
                m["model_type"] == model_type
                and m["version"] != version
                and m.get("is_production", False)
            ):
                m["is_production"] = False
        
        # Mark this version as production
        model["is_production"] = True
        model["promoted_at"] = datetime.utcnow().isoformat() + "Z"
        
        self._save_registry()
        logger.info(f"Promoted {model_type}_{version} to production")
        return True

