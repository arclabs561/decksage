#!/usr/bin/env python3
"""
Integration tests for cache invalidation with prompt versioning.

Tests that:
1. Cache keys include prompt version
2. Cache entries are invalidated when prompt version changes
3. Cache invalidation works across different scripts
4. Game parameter is included in cache keys
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

try:
    from ml.utils.cache_invalidation import CacheInvalidationStrategy, get_prompt_version_hash
    from ml.evaluation.expanded_judge_criteria import get_prompt_version, _PROMPT_VERSION
    HAS_CACHE_INVALIDATION = True
except ImportError:
    HAS_CACHE_INVALIDATION = False
    pytestmark = pytest.mark.skip("Cache invalidation not available")


@pytest.fixture
def cache_strategy():
    """Create a cache invalidation strategy for testing."""
    return CacheInvalidationStrategy(
        prompt_version="2.1.0",
        max_age_days=30,
    )


@pytest.fixture
def mock_cache():
    """Create a mock cache for testing."""
    return {}


class TestCacheKeyGeneration:
    """Test cache key generation includes version info."""
    
    def test_cache_key_includes_prompt_version(self, cache_strategy):
        """Cache key should include prompt version."""
        key = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        assert "prompt_v2.1.0" in key
    
    def test_cache_key_includes_game(self, cache_strategy):
        """Cache key should include game parameter."""
        key = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        assert "magic" in key
    
    def test_cache_key_includes_judge_id(self, cache_strategy):
        """Cache key should include judge ID for isolation."""
        key1 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        key2 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=1,
        )
        assert key1 != key2
    
    def test_cache_key_includes_use_case(self, cache_strategy):
        """Cache key should include use case if provided."""
        key1 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        key2 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case="budget_substitute",
            game="magic",
            judge_id=0,
        )
        assert key1 != key2
    
    def test_different_games_different_keys(self, cache_strategy):
        """Different games should produce different cache keys."""
        key_magic = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        key_pokemon = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="pokemon",
            judge_id=0,
        )
        assert key_magic != key_pokemon


class TestCacheInvalidation:
    """Test cache invalidation logic."""
    
    def test_invalidate_on_prompt_version_mismatch(self, cache_strategy):
        """Cache should be invalidated when prompt version changes."""
        # Create cache entry with old version
        cache_entry = {
            "data": {"highly_relevant": ["Chain Lightning"]},
            "prompt_version": "2.0.0",
            "timestamp": "2024-01-01T00:00:00",
        }
        
        # Should invalidate because version doesn't match
        assert cache_strategy.should_invalidate(
            cache_entry,
            current_prompt_version="2.1.0",
        ) is True
    
    def test_keep_cache_on_same_version(self, cache_strategy):
        """Cache should be kept when prompt version matches."""
        from datetime import datetime, timedelta
        
        # Use recent timestamp to avoid age-based invalidation
        recent_timestamp = (datetime.now() - timedelta(days=1)).isoformat()
        cache_entry = {
            "data": {"highly_relevant": ["Chain Lightning"]},
            "prompt_version": "2.1.0",
            "timestamp": recent_timestamp,
        }
        
        # Should not invalidate because version matches and entry is recent
        assert cache_strategy.should_invalidate(
            cache_entry,
            current_prompt_version="2.1.0",
        ) is False
    
    def test_invalidate_on_age(self, cache_strategy):
        """Cache should be invalidated when too old."""
        from datetime import datetime, timedelta
        
        old_timestamp = (datetime.now() - timedelta(days=31)).isoformat()
        cache_entry = {
            "data": {"highly_relevant": ["Chain Lightning"]},
            "prompt_version": "2.1.0",
            "timestamp": old_timestamp,
        }
        
        # Should invalidate because too old
        assert cache_strategy.should_invalidate(
            cache_entry,
            current_prompt_version="2.1.0",
        ) is True
    
    def test_annotate_cache_entry(self, cache_strategy):
        """Cache entry should be annotated with version and timestamp."""
        entry = {"data": {"highly_relevant": ["Chain Lightning"]}}
        annotated = cache_strategy.annotate_cache_entry(
            entry,
            prompt_version="2.1.0",
        )
        
        assert "timestamp" in annotated
        assert annotated["prompt_version"] == "2.1.0"
        assert annotated["data"] == entry["data"]


class TestPromptVersionIntegration:
    """Test integration with prompt version system."""
    
    def test_get_prompt_version(self):
        """Should retrieve current prompt version."""
        version = get_prompt_version()
        assert version == _PROMPT_VERSION
        assert isinstance(version, str)
        assert len(version) > 0
    
    def test_prompt_version_hash(self):
        """Should generate consistent hash from prompt text."""
        prompt1 = "Test prompt"
        prompt2 = "Test prompt"
        prompt3 = "Different prompt"
        
        hash1 = get_prompt_version_hash(prompt1)
        hash2 = get_prompt_version_hash(prompt2)
        hash3 = get_prompt_version_hash(prompt3)
        
        assert hash1 == hash2  # Same prompt = same hash
        assert hash1 != hash3  # Different prompt = different hash
        assert len(hash1) == 8  # Should be 8 characters


class TestCacheInvalidationWithRealCache:
    """Test cache invalidation with actual cache implementation."""
    
    def test_cache_invalidation_workflow(self, cache_strategy, mock_cache):
        """Test full cache invalidation workflow."""
        query = "Lightning Bolt"
        game = "magic"
        judge_id = 0
        
        # Generate cache key
        cache_key = cache_strategy.get_cache_key(
            query=query,
            use_case=None,
            game=game,
            judge_id=judge_id,
        )
        
        # Create old cache entry
        old_entry = {
            "data": {"highly_relevant": ["Chain Lightning"]},
            "prompt_version": "2.0.0",
            "timestamp": "2024-01-01T00:00:00",
        }
        mock_cache[cache_key] = old_entry
        
        # Check if should invalidate
        cached = mock_cache.get(cache_key)
        if cached and cache_strategy.should_invalidate(
            cached,
            current_prompt_version="2.1.0",
        ):
            # Invalidate
            del mock_cache[cache_key]
            cached = None
        
        assert cached is None  # Should be invalidated
        
        # Generate new entry
        new_data = {"highly_relevant": ["Chain Lightning", "Shock"]}
        new_entry = cache_strategy.annotate_cache_entry(
            {"data": new_data},
            prompt_version="2.1.0",
        )
        mock_cache[cache_key] = new_entry
        
        # Should not invalidate now
        cached = mock_cache.get(cache_key)
        assert cached is not None
        assert not cache_strategy.should_invalidate(
            cached,
            current_prompt_version="2.1.0",
        )


class TestCrossScriptCompatibility:
    """Test that cache invalidation works across different scripts."""
    
    def test_cache_key_consistency(self, cache_strategy):
        """Cache keys should be consistent across scripts."""
        # Simulate key generation from generate_labels_multi_judge.py
        key1 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        
        # Simulate key generation from parallel_multi_judge.py (if it had caching)
        key2 = cache_strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        
        assert key1 == key2  # Should be identical
    
    def test_version_propagation(self):
        """Prompt version should be accessible from all scripts."""
        from ml.evaluation.expanded_judge_criteria import get_prompt_version
        from ml.utils.cache_invalidation import CacheInvalidationStrategy
        
        version = get_prompt_version()
        strategy = CacheInvalidationStrategy(prompt_version=version)
        
        assert strategy.prompt_version == version


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




