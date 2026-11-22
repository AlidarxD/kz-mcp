"""Shared runtime services (HTTP client, cache) with an explicit lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from kz_mcp.settings import Settings
from kz_mcp.upstream.cache import Cache, build_cache
from kz_mcp.upstream.fetch import Upstream

ALMATY = ZoneInfo("Asia/Almaty")


class Services:
    def __init__(
        self,
        settings: Settings,
        cache: Cache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_initial_s: float = 0.3,
    ) -> None:
        self.settings = settings
        self._cache = cache
        self._transport = transport
        self._backoff = backoff_initial_s
        self._upstream: Upstream | None = None

    @property
    def upstream(self) -> Upstream:
        # Created lazily inside the running event loop.
        if self._upstream is None:
            s = self.settings
            http = httpx.AsyncClient(
                timeout=httpx.Timeout(s.http_timeout_s, connect=s.http_connect_timeout_s),
                transport=self._transport,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
            self._upstream = Upstream(
                http,
                self._cache or build_cache(s.redis_url),
                retries=s.http_retries,
                backoff_initial_s=self._backoff,
                offline=s.offline,
                key_prefix=s.cache_prefix,
            )
        return self._upstream

    def today(self) -> date:
        """Business date in Kazakhstan, which drives NBK publication."""
        return datetime.now(ALMATY).date()

    async def aclose(self) -> None:
        if self._upstream is not None:
            await self._upstream.http.aclose()
            await self._upstream.cache.aclose()
            self._upstream = None

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[Services]:
        try:
            yield self
        finally:
            await self.aclose()
