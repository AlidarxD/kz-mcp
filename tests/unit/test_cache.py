import fakeredis
import pytest

from kz_mcp.upstream.cache import CacheUnavailableError, MemoryCache, RedisCache, build_cache

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


async def test_memory_cache_ttl_and_lru():
    clock = Clock()
    cache = MemoryCache(max_entries=2, clock=clock)
    await cache.set("a", "1", ttl_s=10)
    assert await cache.get("a") == "1"
    clock.t = 10
    assert await cache.get("a") is None  # expired
    await cache.set("a", "1", 100)
    await cache.set("b", "2", 100)
    await cache.get("a")  # a is now most recent
    await cache.set("c", "3", 100)  # evicts b
    assert await cache.get("b") is None
    assert await cache.get("a") == "1" and await cache.get("c") == "3"
    await cache.aclose()
    assert await cache.get("a") is None


async def test_redis_cache_roundtrip_with_ttl():
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    cache = RedisCache(fake)
    await cache.set("k", "значение", ttl_s=60)
    assert await cache.get("k") == "значение"
    assert 0 < await fake.ttl("k") <= 60
    assert await cache.get("missing") is None
    await cache.aclose()


class _Broken:
    async def get(self, key):
        raise ConnectionError("down")

    async def set(self, key, value, ex):
        raise ConnectionError("down")

    async def aclose(self):
        raise ConnectionError("down")


async def test_redis_failures_surface_as_cache_unavailable():
    cache = RedisCache(_Broken())
    with pytest.raises(CacheUnavailableError):
        await cache.get("k")
    with pytest.raises(CacheUnavailableError):
        await cache.set("k", "v", 1)
    await cache.aclose()  # best effort, no raise


def test_build_cache():
    assert build_cache(None).name == "memory"
    assert build_cache("redis://localhost:6390/0").name == "redis"
