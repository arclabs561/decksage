from ..utils.llm_cache import LLMCache, LLMCacheConfig, cached_call


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


