"""The fallback chain: cache -> live (timeout, retry) -> stale -> snapshot -> unavailable."""

from datetime import UTC, datetime

import httpx
import pytest

from kz_mcp.upstream.cache import CacheUnavailableError, MemoryCache
from kz_mcp.upstream.fetch import FetchPolicy, Upstream, UpstreamUnavailableError
from kz_mcp.upstream.snapshots import Snapshot

pytestmark = pytest.mark.anyio

URL = "https://upstream.test/data"
SNAP = Snapshot(URL, {"q": "snap"}, "snapshot-body", datetime(2026, 11, 20, tzinfo=UTC))


class Server:
    """Scripted upstream: each request pops the next behaviour."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, text=body)


def make(server, cache=None, offline=False, retries=3):
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return Upstream(
        http,
        cache or MemoryCache(),
        retries=retries,
        backoff_initial_s=0,
        backoff_max_s=0,
        offline=offline,
    )


def policy(scope="exact", snapshot=SNAP, cache_if=lambda b: True):
    return FetchPolicy(
        "test",
        ttl_s=60,
        stale_ttl_s=600,
        snapshot=snapshot,
        snapshot_scope=scope,
        cache_if=cache_if,
    )


async def test_live_then_cache():
    server = Server((200, "fresh"))
    up = make(server)
    first = await up.fetch(policy(), URL, {"q": "1"})
    second = await up.fetch(policy(), URL, {"q": "1"})
    assert (first.status, first.body) == ("live", "fresh")
    assert (second.status, second.body) == ("cache", "fresh")
    assert second.fetched_at == first.fetched_at
    assert server.calls == 1
    assert up.stats.hits == 1 and up.stats.misses == 1
    assert up.stats.by_source["test"]["hits"] == 1


@pytest.mark.parametrize(
    "failure",
    [(503, ""), (429, ""), (500, ""), httpx.ReadTimeout("slow"), httpx.ConnectError("refused")],
)
async def test_transient_failures_are_retried(failure):
    server = Server(failure, failure, (200, "ok"))
    up = make(server)
    got = await up.fetch(policy(), URL, {"q": "1"})
    assert got.body == "ok" and server.calls == 3


async def test_client_errors_are_not_retried():
    server = Server((404, "nope"))
    up = make(server)
    with pytest.raises(UpstreamUnavailableError):
        await up.fetch(policy(), URL, {"q": "1"})
    assert server.calls == 1


async def test_stale_copy_served_when_upstream_fails():
    cache = MemoryCache()
    up = make(Server((200, "good")), cache=cache)
    await up.fetch(policy(), URL, {"q": "1"})
    # fresh entry expires, stale entry survives
    key = up._key("test", URL, {"q": "1"})
    await cache.set(key, "", ttl_s=-1)
    up.http = httpx.AsyncClient(transport=httpx.MockTransport(Server((503, ""))))
    got = await up.fetch(policy(), URL, {"q": "1"})
    assert (got.status, got.body) == ("stale", "good")


async def test_snapshot_exact_scope():
    up = make(Server((503, "")))
    got = await up.fetch(policy(), URL, {"q": "snap"})
    assert (got.status, got.body) == ("snapshot", "snapshot-body")
    assert got.fetched_at == SNAP.recorded_at
    with pytest.raises(UpstreamUnavailableError, match="test is unavailable"):
        await up.fetch(policy(), URL, {"q": "other"})


async def test_snapshot_any_scope_and_no_snapshot():
    up = make(Server(httpx.ConnectError("down")))
    got = await up.fetch(policy(scope="any"), URL, {"q": "other"})
    assert got.status == "snapshot" and got.params == {"q": "snap"}
    with pytest.raises(UpstreamUnavailableError):
        await up.fetch(policy(snapshot=None), URL, {"q": "other"})


async def test_malformed_live_body_counts_as_failure():
    def check(body):
        if body != "valid":
            raise ValueError("bad")

    up = make(Server((200, "<html>maintenance</html>")))
    got = await up.fetch(policy(), URL, {"q": "snap"}, parse_check=check)
    assert got.status == "snapshot"


async def test_cache_if_false_is_not_cached():
    server = Server((200, "empty"))
    up = make(server)
    await up.fetch(policy(cache_if=lambda b: False), URL, {"q": "1"})
    await up.fetch(policy(cache_if=lambda b: False), URL, {"q": "1"})
    assert server.calls == 2


async def test_offline_mode_never_touches_the_network():
    server = Server((200, "live"))
    up = make(server, offline=True)
    got = await up.fetch(policy(), URL, {"q": "snap"})
    assert got.status == "snapshot" and server.calls == 0


class BrokenCache(MemoryCache):
    async def get(self, key):
        raise CacheUnavailableError

    async def set(self, key, value, ttl_s):
        raise CacheUnavailableError


async def test_cache_outage_degrades_to_live():
    server = Server((200, "live"))
    up = make(server, cache=BrokenCache())
    got = await up.fetch(policy(), URL, {"q": "1"})
    assert got.status == "live"
    assert up.stats.errors >= 2


async def test_corrupt_cache_entry_is_ignored():
    cache = MemoryCache()
    up = make(Server((200, "live")), cache=cache)
    await cache.set(up._key("test", URL, {"q": "1"}), "not json", 60)
    assert (await up.fetch(policy(), URL, {"q": "1"})).status == "live"
