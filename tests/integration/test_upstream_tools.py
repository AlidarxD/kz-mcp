"""exchange_rates and company_by_bin end to end through the MCP client, against recorded
upstream responses, with the Redis cache backend (fakeredis)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import fakeredis
import httpx
import pytest
from mcp import Client

from kz_mcp.retrieval import FixtureRetriever
from kz_mcp.server import build_server
from kz_mcp.services import Services
from kz_mcp.settings import Settings
from kz_mcp.upstream.cache import RedisCache
from tests.cassettes import Replay

pytestmark = pytest.mark.anyio

ALL = (
    "nbk_2026-11-20",
    "nbk_2026-12-01_empty",
    "egov_gbd_ul_000740000728",
    "egov_gbd_ul_990140000007_empty",
)


class FrozenServices(Services):
    def __init__(self, *args, today: date, **kwargs):
        super().__init__(*args, **kwargs)
        self._today = today

    def today(self) -> date:
        return self._today


@pytest.fixture
def redis() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis(decode_responses=True)


def _client(replay: Replay, redis, today=date(2026, 11, 20)) -> Client:
    settings = Settings(retriever="fixture", _env_file=None)
    services = FrozenServices(
        settings,
        cache=RedisCache(redis),
        transport=replay.transport,
        backoff_initial_s=0,
        today=today,
    )
    return Client(build_server(settings, FixtureRetriever(), services))


@pytest.fixture
async def recorded(redis) -> AsyncIterator[tuple[Client, Replay]]:
    replay = Replay(*ALL)
    async with _client(replay, redis) as client:
        yield client, replay


async def test_exchange_rates_live_then_cached(recorded, redis):
    client, replay = recorded
    r = await client.call_tool("exchange_rates", {"currencies": ["usd", "EUR", "XYZ"]})
    assert not r.is_error, r.content
    out = r.structured_content
    assert out["date"] == out["requested_date"] == "2026-11-20"
    assert {x["code"] for x in out["rates"]} == {"USD", "EUR"}
    assert out["missing"] == ["XYZ"]
    assert out["source"]["status"] == "live" and out["notice"] is None
    usd = next(x for x in out["rates"] if x["code"] == "USD")
    assert usd["kzt_per_unit"] == pytest.approx(usd["rate"] / usd["quant"])

    again = await client.call_tool("exchange_rates", {"date": "2026-11-20"})
    assert again.structured_content["source"]["status"] == "cache"
    assert len(again.structured_content["rates"]) >= 30
    assert len(replay.requests) == 1
    keys = [k async for k in redis.scan_iter("kzmcp:nbk:*")]
    assert len(keys) == 2  # fresh + stale copies


async def test_exchange_rates_not_published_is_a_tool_error(redis):
    async with _client(Replay(*ALL), redis, today=date(2026, 11, 30)) as client:
        r = await client.call_tool("exchange_rates", {"date": "2026-12-01"})
        assert r.is_error and "not published" in r.content[0].text
        future = await client.call_tool("exchange_rates", {"date": "2026-12-05"})
        assert future.is_error and "up to tomorrow" in future.content[0].text


@pytest.mark.parametrize(
    "args", [{"date": "1990-01-01"}, {"currencies": ["US"]}, {"currencies": []}, {"date": "x"}]
)
async def test_exchange_rates_input_validation(recorded, args):
    client, replay = recorded
    r = await client.call_tool("exchange_rates", args)
    assert r.is_error and not replay.requests


async def test_exchange_rates_falls_back_to_snapshot_when_nbk_is_down(redis):
    replay = Replay(fail=lambda req: httpx.Response(503))
    async with _client(replay, redis, today=date(2026, 11, 25)) as client:
        r = await client.call_tool("exchange_rates", {"currencies": ["USD"]})
    assert not r.is_error
    out = r.structured_content
    assert out["source"]["status"] == "snapshot"
    assert out["requested_date"] == "2026-11-25" and out["date"] == "2026-11-20"
    assert "could not be reached" in out["notice"]
    assert len(replay.requests) == 3  # retried before falling back


async def test_company_found(recorded):
    client, _ = recorded
    r = await client.call_tool("company_by_bin", {"bin": "0007 4000 0728"})
    assert not r.is_error, r.content
    out = r.structured_content
    assert out["bin"] == "000740000728" and out["found"] is True
    assert out["entity_type"] == "resident_legal_entity"
    rec = out["records"][0]
    assert "Национальные информационные технологии" in rec["name_ru"]
    assert rec["registered_on"] == "2000-07-02" and rec["director"]
    assert out["source"]["status"] == "live" and "data.egov.kz" in out["notice"]


async def test_company_not_found_is_not_an_error(recorded):
    client, _ = recorded
    r = await client.call_tool("company_by_bin", {"bin": "990140000007"})
    assert not r.is_error
    assert r.structured_content["found"] is False and r.structured_content["records"] == []


@pytest.mark.parametrize("bin_", ["000740000729", "12345", "abcdefghijkl", "900101300121"])
async def test_company_invalid_bin_never_hits_the_network(recorded, bin_):
    client, replay = recorded
    r = await client.call_tool("company_by_bin", {"bin": bin_})
    assert r.is_error
    assert not replay.requests


async def test_company_outage_uses_snapshot_only_for_the_recorded_bin(redis):
    replay = Replay(fail=lambda req: httpx.Response(502))
    async with _client(replay, redis) as client:
        known = await client.call_tool("company_by_bin", {"bin": "000740000728"})
        unknown = await client.call_tool("company_by_bin", {"bin": "990140000007"})
    assert known.structured_content["source"]["status"] == "snapshot"
    assert "could not be reached" in known.structured_content["notice"]
    assert unknown.is_error and "temporarily unavailable" in unknown.content[0].text


async def test_company_outage_serves_stale_copy(redis):
    async with _client(Replay(*ALL), redis) as client:
        await client.call_tool("company_by_bin", {"bin": "990140000007"})
    # expire fresh copies, keep stale ones
    async for key in redis.scan_iter("kzmcp:egov_gbd_ul:*"):
        if not key.endswith(":stale"):
            await redis.delete(key)
    async with _client(Replay(fail=lambda r: httpx.Response(500)), redis) as client:
        r = await client.call_tool("company_by_bin", {"bin": "990140000007"})
    assert not r.is_error
    assert r.structured_content["source"]["status"] == "stale"


async def test_unexpected_crash_is_masked(redis):
    def explode(request):
        raise RuntimeError("secret internal detail")

    async with _client(Replay(fail=explode), redis) as client:
        r = await client.call_tool("company_by_bin", {"bin": "990140000007"})
    assert r.is_error
    assert "secret" not in r.content[0].text and "Traceback" not in r.content[0].text
