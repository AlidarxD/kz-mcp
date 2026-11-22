"""data.egov.kz open data: State Database of Legal Entities (dataset `gbd_ul`, v1).

The keyless `api/detailed/<dataset>/<version>` endpoint takes an Elasticsearch query in the
`source` parameter. (The `api/v4` endpoints need a registered API key.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from kz_mcp.upstream.fetch import Fetched, FetchPolicy, Upstream
from kz_mcp.upstream.snapshots import load_snapshot

SOURCE = "egov_gbd_ul"
GBD_UL_URL = "https://data.egov.kz/api/detailed/gbd_ul/v1"
MAX_RECORDS = 10


@dataclass(frozen=True)
class CompanyRecord:
    bin: str
    name_ru: str | None
    name_kk: str | None
    director: str | None
    activity_ru: str | None
    activity_kk: str | None
    address_ru: str | None
    address_kk: str | None
    status_ru: str | None
    status_kk: str | None
    registered_on: date | None


def _text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _date(value: Any) -> date | None:
    try:  # "2000-07-02" or "2000-07-02+06:00"
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def query_params(bin_: str) -> dict[str, str]:
    query = {"size": MAX_RECORDS, "query": {"term": {"bin": bin_}}}
    return {"source": json.dumps(query, separators=(",", ":"))}


def parse_companies(body: str, bin_: str) -> list[CompanyRecord]:
    """Raises ValueError if the payload is not the expected shape."""
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("unexpected payload")
    seen: set[tuple[Any, ...]] = set()
    records = []
    for raw in payload["data"]:
        if not isinstance(raw, dict) or str(raw.get("bin", "")) != bin_:
            continue
        rec = CompanyRecord(
            bin=bin_,
            name_ru=_text(raw, "nameru"),
            name_kk=_text(raw, "namekz"),
            director=_text(raw, "director"),
            activity_ru=_text(raw, "okedru"),
            activity_kk=_text(raw, "okedkz"),
            address_ru=_text(raw, "addressru"),
            address_kk=_text(raw, "addresskz"),
            status_ru=_text(raw, "statusru"),
            status_kk=_text(raw, "statuskz"),
            registered_on=_date(raw.get("datereg")),
        )
        key = tuple(vars(rec).values())
        if key not in seen:
            seen.add(key)
            records.append(rec)
    return records


async def fetch_company(
    upstream: Upstream, bin_: str, ttl_s: int, stale_ttl_s: int
) -> tuple[list[CompanyRecord], Fetched]:
    policy = FetchPolicy(
        source=SOURCE,
        ttl_s=ttl_s,
        stale_ttl_s=stale_ttl_s,
        snapshot=load_snapshot("egov_gbd_ul.json"),
        snapshot_scope="exact",
    )
    fetched = await upstream.fetch(
        policy, GBD_UL_URL, query_params(bin_), parse_check=lambda b: parse_companies(b, bin_)
    )
    return parse_companies(fetched.body, bin_), fetched
