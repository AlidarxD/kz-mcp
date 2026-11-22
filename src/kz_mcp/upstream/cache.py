"""Response cache: Redis when configured, an in-process TTL cache otherwise.

The cache is an optimisation and a fallback store, never a dependency: a Redis outage is
logged and treated as a miss, so tools keep working against the upstream.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    errors: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, source: str, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)
        counts = self.by_source.setdefault(source, {"hits": 0, "misses": 0, "errors": 0})
        counts[outcome] += 1


class Cache(Protocol):
    name: str

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_s: int) -> None: ...

    async def aclose(self) -> None: ...


class MemoryCache:
    """Bounded LRU with per-entry TTL. Per process: fine for stdio and tests, not shared
    between HTTP replicas."""

    name = "memory"

    def __init__(self, max_entries: int = 2048, clock: Callable[[], float] = time.monotonic):
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._max = max_entries
        self._clock = clock

    async def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= self._clock():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self._data[key] = (self._clock() + ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    async def aclose(self) -> None:
        self._data.clear()


class RedisCache:
    name = "redis"

    def __init__(self, client: object) -> None:
        # redis.asyncio.Redis; typed loosely so redis stays an import-time-optional detail
        self._redis = client

    @classmethod
    def from_url(cls, url: str, timeout_s: float = 0.5) -> RedisCache:
        from redis.asyncio import Redis

        return cls(
            Redis.from_url(
                url,
                socket_timeout=timeout_s,
                socket_connect_timeout=timeout_s,
                decode_responses=True,
            )
        )

    async def get(self, key: str) -> str | None:
        try:
            value = await self._redis.get(key)  # type: ignore[attr-defined]
        except Exception as exc:  # any Redis/network failure degrades to a miss
            log.warning("redis get failed: %s", type(exc).__name__)
            raise CacheUnavailableError from exc
        return None if value is None else str(value)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_s)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("redis set failed: %s", type(exc).__name__)
            raise CacheUnavailableError from exc

    async def aclose(self) -> None:
        # closing a broken connection is best effort
        with contextlib.suppress(Exception):
            await self._redis.aclose()  # type: ignore[attr-defined]


class CacheUnavailableError(Exception):
    pass


def build_cache(redis_url: str | None) -> Cache:
    if redis_url:
        return RedisCache.from_url(redis_url)
    return MemoryCache()
