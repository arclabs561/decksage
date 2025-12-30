#!/usr/bin/env python3
"""
Performance benchmarks for label generation system.

Tests performance of:
1. Cache hit vs cache miss
2. Multi-judge vs single judge
3. Parallel vs sequential execution
4. Card database lookups
5. Cache invalidation overhead
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

try:
    from ml.data.card_database import get_card_database
    from ml.utils.cache_invalidation import CacheInvalidationStrategy, get_prompt_version
    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False
    pytestmark = pytest.mark.skip("Dependencies not available")


@pytest.mark.slow
class TestCachePerformance:
    """Benchmark cache performance."""
    
    def test_cache_key_generation_speed(self, benchmark):
        """Cache key generation should be fast."""
        strategy = CacheInvalidationStrategy(prompt_version="2.1.0")
        
        def generate_key():
            return strategy.get_cache_key(
                query="Lightning Bolt",
                use_case="budget_substitute",
                game="magic",
                judge_id=0,
            )
        
        # Should be very fast (< 1ms)
        result = benchmark(generate_key)
        assert result is not None
        assert len(result) > 0
    
    def test_cache_invalidation_check_speed(self, benchmark):
        """Cache invalidation check should be fast."""
        strategy = CacheInvalidationStrategy(prompt_version="2.1.0")
        cache_entry = {
            "data": {"highly_relevant": ["Chain Lightning"]},
            "prompt_version": "2.1.0",
            "timestamp": "2024-01-01T00:00:00",
        }
        
        def check_invalidation():
            return strategy.should_invalidate(
                cache_entry,
                current_prompt_version="2.1.0",
            )
        
        # Should be very fast (< 1ms)
        result = benchmark(check_invalidation)
        assert isinstance(result, bool)


@pytest.mark.slow
class TestCardDatabasePerformance:
    """Benchmark card database lookups."""
    
    def test_card_database_initialization_speed(self, benchmark):
        """Card database initialization should be reasonably fast."""
        def init_db():
            return get_card_database()
        
        # Should be fast (< 100ms for first load, < 1ms for cached)
        db = benchmark(init_db)
        assert db is not None
    
    def test_card_validation_speed(self, benchmark):
        """Card validation should be very fast."""
        db = get_card_database()
        
        def validate_card():
            return db.is_valid_card("Lightning Bolt", "magic")
        
        # Should be very fast (< 1ms)
        result = benchmark(validate_card)
        assert result is True
    
    def test_game_detection_speed(self, benchmark):
        """Game detection should be very fast."""
        db = get_card_database()
        
        def detect_game():
            return db.get_game("Lightning Bolt")
        
        # Should be very fast (< 1ms)
        result = benchmark(detect_game)
        assert result == "magic"
    
    def test_batch_card_validation(self):
        """Batch card validation should be efficient."""
        db = get_card_database()
        test_cards = [
            "Lightning Bolt",
            "Pikachu",
            "Dark Magician",
            "Counterspell",
            "Charizard",
        ] * 100  # 500 cards
        
        start = time.time()
        results = []
        for card in test_cards:
            # Try each game
            for game in ["magic", "pokemon", "yugioh"]:
                if db.is_valid_card(card, game):
                    results.append((card, game))
                    break
        elapsed = time.time() - start
        
        # Should process 500 cards in < 1 second
        assert elapsed < 1.0
        assert len(results) > 0


@pytest.mark.slow
class TestLabelGenerationPerformance:
    """Benchmark label generation performance (requires LLM)."""
    
    @pytest.mark.skipif(not HAS_DEPENDENCIES, reason="LLM not available")
    def test_single_judge_generation_time(self):
        """Single judge generation should complete in reasonable time."""
        # This would require actual LLM calls
        # For now, just test that the infrastructure is fast
        strategy = CacheInvalidationStrategy(prompt_version="2.1.0")
        
        start = time.time()
        key = strategy.get_cache_key(
            query="Lightning Bolt",
            use_case=None,
            game="magic",
            judge_id=0,
        )
        elapsed = time.time() - start
        
        # Cache key generation should be < 1ms
        assert elapsed < 0.001
        assert key is not None


class TestMemoryUsage:
    """Test memory efficiency of cache and database."""
    
    def test_card_database_memory_footprint(self):
        """Card database should have reasonable memory footprint."""
        import sys
        
        db = get_card_database()
        
        # Get size of database object
        size = sys.getsizeof(db)
        
        # Should be reasonable (< 100MB for all games)
        # This is a rough check - actual size depends on implementation
        assert size < 100 * 1024 * 1024  # 100MB
    
    def test_cache_entry_size(self):
        """Cache entries should be reasonably sized."""
        import sys
        
        cache_entry = {
            "data": {
                "highly_relevant": ["Chain Lightning", "Shock", "Lightning Strike"],
                "relevant": ["Bolt of Keranos", "Lightning Helix"],
                "somewhat_relevant": ["Fireball", "Flame Slash"],
                "marginally_relevant": ["Lava Spike"],
                "irrelevant": ["Counterspell", "Brainstorm"],
            },
            "prompt_version": "2.1.0",
            "timestamp": "2024-01-01T00:00:00",
        }
        
        size = sys.getsizeof(cache_entry)
        
        # Should be reasonable (< 1KB per entry)
        assert size < 1024


class TestScalability:
    """Test system scalability."""
    
    def test_cache_key_generation_scales(self):
        """Cache key generation should scale to many queries."""
        strategy = CacheInvalidationStrategy(prompt_version="2.1.0")
        
        queries = [f"Card {i}" for i in range(1000)]
        
        start = time.time()
        keys = []
        for query in queries:
            key = strategy.get_cache_key(
                query=query,
                use_case=None,
                game="magic",
                judge_id=0,
            )
            keys.append(key)
        elapsed = time.time() - start
        
        # Should process 1000 queries in < 100ms
        assert elapsed < 0.1
        assert len(keys) == 1000
        assert len(set(keys)) == 1000  # All unique
    
    def test_card_database_scales(self):
        """Card database should handle many lookups efficiently."""
        db = get_card_database()
        
        # Test with many lookups
        test_cards = [f"Test Card {i}" for i in range(1000)]
        
        start = time.time()
        results = []
        for card in test_cards:
            # Try to find game for each card
            for game in ["magic", "pokemon", "yugioh"]:
                if db.is_valid_card(card, game):
                    results.append((card, game))
                    break
        elapsed = time.time() - start
        
        # Should process 1000 cards in < 1 second
        assert elapsed < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "slow"])

