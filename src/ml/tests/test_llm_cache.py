"""Tests for deterministic LLM cache behavior."""

from pathlib import Path

from ..utils.llm_cache import (
    LLMCache,
    LLMCacheConfig,
    cached_call,
    make_openrouter_payload,
)


def test_llm_cache_hit(tmp_path, monkeypatch):
    """First call computes and stores; second call returns cached value."""
    # Isolate cache to a temp directory
    monkeypatch.setenv("LLM_CACHE_DIR", str(Path(tmp_path)))
    monkeypatch.setenv("LLM_CACHE_BYPASS", "0")

    cache = LLMCache()

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"value": 42}

    payload = make_openrouter_payload(
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
        params={"temperature": 0},
    )

    first = cached_call(cache, payload, compute)
    second = cached_call(cache, payload, compute)

    assert first == second == {"value": 42}
    assert calls["n"] == 1  # second call should be a cache hit


def test_cached_call_basic(tmp_path):
    cfg = LLMCacheConfig(cache_dir=tmp_path / "cache", size_limit_mb=1, ttl_seconds=60, bypass=False)
    cache = LLMCache(cfg, scope="test")

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"x": 1}

    payload = {"a": 1}
    v1 = cached_call(cache, payload, compute)
    v2 = cached_call(cache, payload, compute)
    assert v1 == v2 == {"x": 1}
    assert calls["n"] == 1
