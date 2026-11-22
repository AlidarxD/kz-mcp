"""Bundled upstream responses (recorded with scripts/record_cassettes.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib import resources


@dataclass(frozen=True)
class Snapshot:
    url: str
    params: dict[str, str]
    body: str
    recorded_at: datetime


@cache
def load_snapshot(name: str) -> Snapshot:
    raw = json.loads(resources.files("kz_mcp.snapshots").joinpath(name).read_text("utf-8"))
    return Snapshot(
        url=raw["request"]["url"],
        params=dict(raw["request"]["params"]),
        body=raw["response"]["body"],
        recorded_at=datetime.fromisoformat(raw["recorded_at"]),
    )
