from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from kz_mcp.models import StrictModel


class SourceInfo(StrictModel):
    name: str = Field(description="Publisher of the data")
    url: str = Field(description="Upstream endpoint")
    status: Literal["live", "cache", "stale", "snapshot"] = Field(
        description="live: fetched now; cache: fresh cached copy; stale: upstream failed, last "
        "good copy served; snapshot: upstream failed, bundled recorded copy served"
    )
    fetched_at: datetime = Field(description="When the data was fetched from the upstream")
