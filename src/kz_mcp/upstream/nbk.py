"""National Bank of Kazakhstan official exchange rates (RSS/XML feed)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from defusedxml import ElementTree

from kz_mcp.upstream.fetch import Fetched, FetchPolicy, Upstream
from kz_mcp.upstream.snapshots import load_snapshot

SOURCE = "nbk"
RATES_URL = "https://nationalbank.kz/rss/get_rates.cfm"

Direction = Literal["up", "down", "unchanged"]
_DIRECTIONS: dict[str, Direction] = {"UP": "up", "DOWN": "down"}


@dataclass(frozen=True)
class Rate:
    code: str
    name: str
    rate: Decimal  # KZT for `quant` units
    quant: int
    change: Decimal | None
    direction: Direction | None


@dataclass(frozen=True)
class RatesDay:
    date: date
    rates: list[Rate]


def _decimal(text: str | None) -> Decimal | None:
    if not text or not text.strip():
        return None
    try:
        return Decimal(text.strip())
    except InvalidOperation:
        return None


def parse_rates(xml: str) -> RatesDay:
    """Parse the feed. Raises ValueError on malformed XML; a valid feed may have no items
    (the date has no published rates yet)."""
    try:
        root = ElementTree.fromstring(xml)
    except SyntaxError as exc:  # xml.etree.ElementTree.ParseError
        raise ValueError("malformed XML") from exc
    if root.tag != "rates":
        raise ValueError(f"unexpected root element {root.tag!r}")
    day = datetime.strptime(root.findtext("date", "").strip(), "%d.%m.%Y").date()
    rates = []
    for item in root.iter("item"):
        code = (item.findtext("title") or "").strip().upper()
        rate = _decimal(item.findtext("description"))
        quant = int((item.findtext("quant") or "1").strip() or 1)
        if len(code) != 3 or rate is None or quant < 1:
            continue
        index = (item.findtext("index") or "").strip().upper()
        change = _decimal(item.findtext("change"))
        direction: Direction | None = _DIRECTIONS.get(index)
        if direction is None and change is not None and change == 0:
            direction = "unchanged"
        rates.append(
            Rate(
                code=code,
                name=(item.findtext("fullname") or "").strip(),
                rate=rate,
                quant=quant,
                change=change,
                direction=direction,
            )
        )
    return RatesDay(date=day, rates=rates)


async def fetch_rates(
    upstream: Upstream, on: date, today: date, ttl_s: int, history_ttl_s: int, stale_ttl_s: int
) -> tuple[RatesDay, Fetched]:
    # Past days never change; today's and tomorrow's feed can still be (re)published.
    policy = FetchPolicy(
        source=SOURCE,
        ttl_s=history_ttl_s if on < today else ttl_s,
        stale_ttl_s=stale_ttl_s,
        snapshot=load_snapshot("nbk_rates.json"),
        snapshot_scope="any",
        cache_if=lambda body: "<item>" in body,  # never cache "not published yet"
    )
    fetched = await upstream.fetch(
        policy, RATES_URL, {"fdate": on.strftime("%d.%m.%Y")}, parse_check=parse_rates
    )
    return parse_rates(fetched.body), fetched
