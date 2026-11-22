from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from mcp import Client

from kz_mcp.retrieval import FixtureRetriever
from kz_mcp.server import build_server
from kz_mcp.settings import Settings


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(retriever="fixture", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[Client]:
    async with Client(build_server(settings, FixtureRetriever())) as c:
        yield c
