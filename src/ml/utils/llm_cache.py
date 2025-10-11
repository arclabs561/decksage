#!/usr/bin/env python3
"""
Deterministic, application-level cache for LLM calls.

Design goals:
- Key by normalized payload (model + system + messages + params)
- Disk-backed persistence with TTL and size limits
- Opt-out via env LLM_CACHE_BYPASS=1
- Provide sync and async wrappers

Env vars:
- LLM_CACHE_DIR (default: .cache/llm_responses)
- LLM_CACHE_SIZE_MB (default: 1024)
- LLM_CACHE_TTL_SECONDS (default: 30 days)
- LLM_CACHE_BYPASS (default: 0)
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypeVar

try:
    from diskcache import Cache  # type: ignore
except Exception as _e:  # pragma: no cover
    Cache = None  # type: ignore


T = TypeVar("T")


def _default_cache_dir() -> Path:
    root = Path(os.getcwd())
    return root / ".cache" / "llm_responses"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "")) if os.getenv(name) is not None else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def make_cache_key(payload: dict) -> str:
    """Generate a stable key for the given payload."""
    body = _canonical_json(payload)
    digest = sha256(body.encode("utf-8")).hexdigest()
    return digest


@dataclass
class LLMCacheConfig:
    cache_dir: Path
    size_limit_mb: int
    ttl_seconds: int
    bypass: bool


def load_config() -> LLMCacheConfig:
    cache_dir = Path(os.getenv("LLM_CACHE_DIR", str(_default_cache_dir())))
    size_limit_mb = _env_int("LLM_CACHE_SIZE_MB", 1024)
    # Default 30 days
    ttl_seconds = _env_int("LLM_CACHE_TTL_SECONDS", 30 * 24 * 3600)
    bypass = _env_bool("LLM_CACHE_BYPASS", False)
    return LLMCacheConfig(cache_dir, size_limit_mb, ttl_seconds, bypass)


class LLMCache:
    def __init__(self, config: Optional[LLMCacheConfig] = None, *, scope: str = "default") -> None:
        self.config = config or load_config()
        cache_path = self.config.cache_dir / scope
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if Cache is None:
            raise ImportError("diskcache not installed; install with: uv add diskcache")
        # Eviction controlled via size_limit on bytes—not strictly enforced here,
        # but we can set a rough size limit with a separate directory quota if desired.
        self._cache = Cache(str(cache_path))

    def get(self, key: str) -> Any | None:
        if self.config.bypass:
            return None
        try:
            return self._cache.get(key, default=None)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if self.config.bypass:
            return
        try:
            expire = int(ttl if ttl is not None else self.config.ttl_seconds)
            self._cache.set(key, value, expire=expire)
        except Exception:
            # Best-effort cache
            pass

    def clear(self) -> None:
        try:
            self._cache.clear()
        except Exception:
            pass

    def stats(self) -> dict:
        try:
            info = self._cache.stats()
        except Exception:
            info = {}
        return {
            "dir": str(self.config.cache_dir),
            "bypass": self.config.bypass,
            "ttl_seconds": self.config.ttl_seconds,
            "size_limit_mb": self.config.size_limit_mb,
            "backend": "diskcache",
            "stats": info,
        }


def cached_call(
    cache: LLMCache,
    payload: dict,
    compute: Callable[[], T],
    *,
    ttl: Optional[int] = None,
    encoder: Callable[[T], Any] | None = None,
    decoder: Callable[[Any], T] | None = None,
) -> T:
    """Cache a synchronous computation based on payload key."""
    key = make_cache_key(payload)
    cached = cache.get(key)
    if cached is not None:
        return decoder(cached) if decoder else cached  # type: ignore[return-value]

    value = compute()
    to_store = encoder(value) if encoder else value
    cache.set(key, to_store, ttl=ttl)
    return value


async def async_cached_call(
    cache: LLMCache,
    payload: dict,
    compute_async: Callable[[], Awaitable[T]],
    *,
    ttl: Optional[int] = None,
    encoder: Callable[[T], Any] | None = None,
    decoder: Callable[[Any], T] | None = None,
) -> T:
    """Cache an async computation based on payload key."""
    key = make_cache_key(payload)
    cached = cache.get(key)
    if cached is not None:
        return decoder(cached) if decoder else cached  # type: ignore[return-value]

    value = await compute_async()
    to_store = encoder(value) if encoder else value
    cache.set(key, to_store, ttl=ttl)
    return value


# Convenience wrappers for OpenRouter-style calls
def make_openrouter_payload(model: str, messages: list[dict], params: dict | None = None) -> dict:
    return {
        "engine": "openrouter",
        "model": model,
        "messages": messages,
        "params": params or {},
        "v": 1,
    }



