"""Resilient upstream fetching: cache → live (timeout, retry with backoff) → stale copy →
bundled snapshot. Every result carries its provenance so clients can tell live data from
fallbacks."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from kz_mcp import __version__
from kz_mcp.upstream.cache import Cache, CacheStats, CacheUnavailableError
from kz_mcp.upstream.snapshots import Snapshot

log = logging.getLogger(__name__)

Status = Literal["live", "cache", "stale", "snapshot"]
USER_AGENT = f"kz-mcp/{__version__} (+https://github.com/AlidarXD/kz-mcp)"


class UpstreamError(Exception):
    """The upstream failed (network, HTTP status, or a response we cannot parse)."""


class UpstreamUnavailableError(Exception):
    """The upstream failed and no fallback could answer this request."""

    def __init__(self, source: str) -> None:
        super().__init__(f"{source} is unavailable and no cached copy exists for this request")
        self.source = source


@dataclass(frozen=True)
class Fetched:
    body: str
    status: Status
    fetched_at: datetime
    url: str
    params: dict[str, str]


@dataclass(frozen=True)
class FetchPolicy:
    source: str
    ttl_s: int
    stale_ttl_s: int
    snapshot: Snapshot | None = None
    # "exact": the snapshot only answers its own recorded request; "any": it answers every
    # request of this source (callers must then flag the mismatch, e.g. a different date).
    snapshot_scope: Literal["exact", "any"] = "exact"
    cache_if: Callable[[str], bool] = lambda body: True


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):  # timeouts, connection errors
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


class Upstream:
    def __init__(
        self,
        http: httpx.AsyncClient,
        cache: Cache,
        *,
        retries: int = 3,
        backoff_initial_s: float = 0.3,
        backoff_max_s: float = 3.0,
        offline: bool = False,
        key_prefix: str = "kzmcp:",
        stats: CacheStats | None = None,
    ) -> None:
        self.http = http
        self.cache = cache
        self.retries = retries
        self.backoff_initial_s = backoff_initial_s
        self.backoff_max_s = backoff_max_s
        self.offline = offline
        self.key_prefix = key_prefix
        self.stats = stats or CacheStats()

    def _key(self, source: str, url: str, params: dict[str, str]) -> str:
        digest = hashlib.sha256(
            json.dumps([url, sorted(params.items())], ensure_ascii=False).encode()
        ).hexdigest()[:24]
        return f"{self.key_prefix}{source}:{digest}"

    async def _cache_get(self, source: str, key: str) -> dict[str, str] | None:
        try:
            raw = await self.cache.get(key)
        except CacheUnavailableError:
            self.stats.record(source, "errors")
            return None
        if raw is None:
            return None
        try:
            record: dict[str, str] = json.loads(raw)
            return record
        except ValueError:
            return None

    async def _cache_set(self, source: str, key: str, record: dict[str, str], ttl: int) -> None:
        try:
            await self.cache.set(key, json.dumps(record, ensure_ascii=False), ttl)
        except CacheUnavailableError:
            self.stats.record(source, "errors")

    async def _get_live(self, url: str, params: dict[str, str]) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.retries),
            wait=wait_exponential_jitter(
                multiplier=self.backoff_initial_s,
                max=self.backoff_max_s,
                jitter=self.backoff_initial_s,
            ),
            retry=retry_if_exception(_retryable),
            reraise=True,
        ):
            with attempt:
                resp = await self.http.get(url, params=params, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
                return resp.text
        raise AssertionError("unreachable")  # pragma: no cover

    def _from_snapshot(self, policy: FetchPolicy, url: str, params: dict[str, str]) -> Fetched:
        snap = policy.snapshot
        if snap is not None and (policy.snapshot_scope == "any" or snap.params == params):
            log.warning("%s: serving bundled snapshot recorded %s", policy.source, snap.recorded_at)
            return Fetched(snap.body, "snapshot", snap.recorded_at, snap.url, snap.params)
        raise UpstreamUnavailableError(policy.source)

    async def fetch(
        self,
        policy: FetchPolicy,
        url: str,
        params: dict[str, str],
        parse_check: Callable[[str], object] | None = None,
    ) -> Fetched:
        """Return the response body for GET url?params, following the fallback chain.
        `parse_check` raises if a body is malformed; malformed live bodies count as failures."""
        if self.offline:
            return self._from_snapshot(policy, url, params)

        key = self._key(policy.source, url, params)
        cached = await self._cache_get(policy.source, key)
        if cached is not None:
            self.stats.record(policy.source, "hits")
            return Fetched(
                cached["body"], "cache", datetime.fromisoformat(cached["at"]), url, params
            )
        self.stats.record(policy.source, "misses")

        try:
            body = await self._get_live(url, params)
            if parse_check is not None:
                try:
                    parse_check(body)
                except Exception as exc:
                    raise UpstreamError(f"{policy.source}: malformed response") from exc
        except (httpx.HTTPError, UpstreamError) as exc:
            log.warning("%s upstream failed: %s", policy.source, type(exc).__name__)
            stale = await self._cache_get(policy.source, key + ":stale")
            if stale is not None:
                return Fetched(
                    stale["body"], "stale", datetime.fromisoformat(stale["at"]), url, params
                )
            return self._from_snapshot(policy, url, params)

        now = datetime.now(UTC)
        if policy.cache_if(body):
            record = {"body": body, "at": now.isoformat()}
            await self._cache_set(policy.source, key, record, policy.ttl_s)
            await self._cache_set(policy.source, key + ":stale", record, policy.stale_ttl_s)
        return Fetched(body, "live", now, url, params)
