from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from kz_mcp.models import StrictModel
from kz_mcp.models.common import SourceInfo


class ExchangeRate(StrictModel):
    code: str = Field(description="ISO 4217 currency code")
    name: str = Field(description="Currency name as published by the National Bank (Russian)")
    kzt_per_unit: float = Field(description="Tenge for one unit of the currency")
    rate: float = Field(description="Official rate: tenge for `quant` units")
    quant: int
    change: float | None = Field(description="Change of `rate` against the previous rate")
    direction: Literal["up", "down", "unchanged"] | None


class ExchangeRatesResult(StrictModel):
    date: dt.date = Field(description="Date the rates apply to")
    requested_date: dt.date
    base: Literal["KZT"] = "KZT"
    rates: list[ExchangeRate]
    missing: list[str] = Field(description="Requested currencies the National Bank does not quote")
    source: SourceInfo
    notice: str | None = Field(description="Set when the data is not the live answer")
