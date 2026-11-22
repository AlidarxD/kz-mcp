"""Spawn `python -m kz_mcp` over stdio and drive it with the MCP client SDK."""

from __future__ import annotations

import os
import sys

import pytest
from mcp import Client, StdioServerParameters

pytestmark = [pytest.mark.anyio, pytest.mark.e2e]


async def test_stdio_server_end_to_end() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("KZ_MCP_")}
    env |= {"KZ_MCP_RETRIEVER": "fixture", "KZ_MCP_LOG_LEVEL": "WARNING"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "kz_mcp"], env=env)
    async with Client(params) as client:
        assert client.server_info is not None and client.server_info.name == "kz-mcp"
        names = {t.name for t in (await client.list_tools()).tools}
        assert {"search_law", "get_law_article"} <= names

        found = await client.call_tool("search_law", {"query": "распитие алкогольных напитков"})
        assert not found.is_error
        top = found.structured_content["results"][0]
        assert top["citation_id"] == "kz-law:K1400000235:ru:440"

        article = await client.call_tool(
            "get_law_article", {"code": "administrative", "article_number": "440"}
        )
        assert article.structured_content["text"].strip()

        bad = await client.call_tool("get_law_article", {"code": "labour", "article_number": "0"})
        assert bad.is_error
