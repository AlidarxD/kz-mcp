"""`exchange_rates`: official National Bank of Kazakhstan rates."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from kz_mcp.models.common import SourceInfo
from kz_mcp.models.rates import ExchangeRate, ExchangeRatesResult
from kz_mcp.services import Services
from kz_mcp.upstream import nbk
from kz_mcp.upstream.fetch import UpstreamUnavailableError

TENGE_INTRODUCED = dt.date(1993, 11, 15)

DESCRIPTION = (
    "Official exchange rates of the National Bank of Kazakhstan: tenge (KZT) per unit of "
    "foreign currency, for a date (default: today in Almaty; the National Bank publishes the "
    "next day's rates in advance). Optionally filter by ISO currency codes."
)

# Reads public data; the answer for a past date never changes. The upstream is external.
REMOTE_READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)

CurrencyCode = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$", description="ISO 4217, e.g. USD")]


def source_info(name: str, fetched: object) -> SourceInfo:
    from kz_mcp.upstream.fetch import Fetched

    assert isinstance(fetched, Fetched)  # noqa: S101
    return SourceInfo(
        name=name, url=fetched.url, status=fetched.status, fetched_at=fetched.fetched_at
    )


def register(server: MCPServer, services: Services) -> None:
    @server.tool(
        title="National Bank exchange rates",
        description=DESCRIPTION,
        annotations=REMOTE_READ_ONLY,
    )
    async def exchange_rates(
        date: Annotated[
            dt.date | None,
            Field(ge=TENGE_INTRODUCED, description="YYYY-MM-DD; default today (Asia/Almaty)"),
        ] = None,
        currencies: Annotated[
            list[CurrencyCode] | None,
            Field(min_length=1, max_length=50, description="Only these currencies"),
        ] = None,
    ) -> ExchangeRatesResult:
        today = services.today()
        requested = date or today
        if requested > today + dt.timedelta(days=1):
            raise ToolError(
                f"No rates for {requested}: the National Bank publishes rates up to tomorrow "
                f"({today + dt.timedelta(days=1)})"
            )
        s = services.settings
        try:
            day, fetched = await nbk.fetch_rates(
                services.upstream,
                requested,
                today,
                ttl_s=s.rates_ttl_s,
                history_ttl_s=s.rates_history_ttl_s,
                stale_ttl_s=s.stale_ttl_s,
            )
        except UpstreamUnavailableError:
            raise ToolError(
                "National Bank rates are temporarily unavailable; try again later"
            ) from None
        if not day.rates:
            raise ToolError(f"The National Bank has not published rates for {requested}")

        wanted = {c.upper() for c in currencies} if currencies else None
        rates = [
            ExchangeRate(
                code=r.code,
                name=r.name,
                kzt_per_unit=float(round(r.rate / r.quant, 6)),
                rate=float(r.rate),
                quant=r.quant,
                change=None if r.change is None else float(r.change),
                direction=r.direction,
            )
            for r in day.rates
            if wanted is None or r.code in wanted
        ]
        notice = None
        if fetched.status in ("stale", "snapshot") or day.date != requested:
            notice = (
                f"The National Bank could not be reached; showing rates for {day.date} from a "
                f"{fetched.status} copy fetched {fetched.fetched_at:%Y-%m-%d %H:%M} UTC, not "
                f"live data for {requested}."
            )
        return ExchangeRatesResult(
            date=day.date,
            requested_date=requested,
            rates=rates,
            missing=sorted(wanted - {r.code for r in rates}) if wanted else [],
            source=source_info("National Bank of the Republic of Kazakhstan", fetched),
            notice=notice,
        )
