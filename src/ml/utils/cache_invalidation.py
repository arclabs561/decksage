"""Cache invalidation strategies for LLM labeling system."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class CacheInvalidationStrategy:
    """Manages cache invalidation for LLM labeling."""
    
    def __init__(
        self,
        prompt_version: str | None = None,
        model_version: str | None = None,
        max_age_days: int = 30,
    ):
        """
        Initialize cache invalidation strategy.
        
        Args:
            prompt_version: Version string for prompts (invalidates on change)
            model_version: Version string for models (invalidates on change)
            max_age_days: Maximum age of cached entries in days
        """
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.max_age_days = max_age_days
    
    def get_cache_key(
        self,
        query: str,
        use_case: str | None,
        game: str | None,
        judge_id: int,
        **kwargs: Any,
    ) -> str:
        """
        Generate cache key with versioning.
        
        Includes versions to automatically invalidate on changes.
        """
        key_parts = [
            "label",
            query,
            use_case or "",
            game or "",
            str(judge_id),
        ]
        
        # Add version info to key
        if self.prompt_version:
            key_parts.append(f"prompt_v{self.prompt_version}")
        if self.model_version:
            key_parts.append(f"model_v{self.model_version}")
        
        # Add any additional kwargs
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        key_string = "_".join(str(p) for p in key_parts)
        
        # Hash if too long
        if len(key_string) > 200:
            key_string = hashlib.md5(key_string.encode()).hexdigest()
        
        return key_string
    
    def should_invalidate(
        self,
        cache_entry: dict[str, Any],
        current_prompt_version: str | None = None,
        current_model_version: str | None = None,
    ) -> bool:
        """
        Check if cache entry should be invalidated.
        
        Returns True if entry is stale or versions don't match.
        """
        # Check age
        if "timestamp" in cache_entry:
            try:
                timestamp = datetime.fromisoformat(cache_entry["timestamp"])
                age = datetime.now() - timestamp
                if age > timedelta(days=self.max_age_days):
                    logger.debug(f"Cache entry too old: {age.days} days")
                    return True
            except (ValueError, TypeError):
                pass
        
        # Check prompt version
        # Use current_prompt_version if provided, otherwise use self.prompt_version
        prompt_version_to_check = current_prompt_version if current_prompt_version is not None else self.prompt_version
        if prompt_version_to_check:
            cache_prompt_version = cache_entry.get("prompt_version")
            if cache_prompt_version is not None and cache_prompt_version != prompt_version_to_check:
                logger.debug("Cache entry prompt version mismatch")
                return True
        
        # Check model version
        # Use current_model_version if provided, otherwise use self.model_version
        model_version_to_check = current_model_version if current_model_version is not None else self.model_version
        if model_version_to_check:
            cache_model_version = cache_entry.get("model_version")
            if cache_model_version is not None and cache_model_version != model_version_to_check:
                logger.debug("Cache entry model version mismatch")
                return True
        
        return False
    
    def annotate_cache_entry(
        self,
        entry: dict[str, Any],
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, Any]:
        """Add metadata to cache entry for future invalidation."""
        annotated = entry.copy()
        annotated["timestamp"] = datetime.now().isoformat()
        
        if prompt_version:
            annotated["prompt_version"] = prompt_version
        if model_version:
            annotated["model_version"] = model_version
        
        return annotated


def get_prompt_version_hash(prompt_text: str) -> str:
    """Generate version hash from prompt text."""
    return hashlib.sha256(prompt_text.encode()).hexdigest()[:8]


def get_model_version(model_name: str) -> str:
    """Extract version from model name or use as-is."""
    # Could parse version from model name if needed
    return model_name




