"""VCR-style replay of recorded upstream responses (tests/integration/cassettes)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

CASSETTES = Path(__file__).parent / "integration" / "cassettes"


def load(name: str) -> dict[str, Any]:
    return json.loads((CASSETTES / f"{name}.json").read_text(encoding="utf-8"))


class Replay:
    """httpx transport answering only requests that match a recorded cassette exactly.
    Unknown requests fail the test; `fail` lets a test simulate upstream outages."""

    def __init__(self, *names: str, fail: Callable[[httpx.Request], httpx.Response] | None = None):
        self.cassettes = [load(n) for n in names]
        self.fail = fail
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail is not None:
            return self.fail(request)
        url = str(request.url.copy_with(query=None))
        params = dict(request.url.params)
        for c in self.cassettes:
            req = c["request"]
            if req["url"] == url and req["params"] == params:
                resp = c["response"]
                return httpx.Response(
                    resp["status"],
                    text=resp["body"],
                    headers={"content-type": resp["content_type"]},
                )
        raise AssertionError(f"unexpected upstream request: {request.url}")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)
