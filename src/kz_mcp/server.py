"""Server assembly: tools, resources and prompts on one `MCPServer`."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import ConfigDict

from kz_mcp import __version__, prompts, resources
from kz_mcp.retrieval import LawRetriever, build_retriever
from kz_mcp.settings import Settings
from kz_mcp.tools import law

INSTRUCTIONS = """\
Tools over Kazakhstan public data. Legislation: search_law finds articles of the
Constitution and the Civil, Labour, Tax, Criminal and Administrative Offences codes in
Russian (ru) or Kazakh (kk); get_law_article returns the full current text. Always cite
articles by citation_id and url, answer only from returned text, and say when the
retrieved articles do not answer the question. Nothing here is legal advice."""


def harden_input_schemas(server: MCPServer) -> None:
    """Reject unknown tool arguments (the SDK ignores them by default) and advertise it
    with `additionalProperties: false`, so schemas are strict on both sides."""
    for tool in server._tool_manager.list_tools():
        base: Any = tool.fn_metadata.arg_model
        strict = type(
            base.__name__,
            (base,),
            {
                "model_config": ConfigDict(extra="forbid", arbitrary_types_allowed=True),
                "__module__": base.__module__,
            },
        )
        tool.fn_metadata.arg_model = strict
        tool.parameters["additionalProperties"] = False


def build_server(
    settings: Settings | None = None, retriever: LawRetriever | None = None
) -> MCPServer:
    settings = settings or Settings()
    retriever = retriever or build_retriever(settings)
    server = MCPServer(
        name="kz-mcp",
        title="Kazakhstan public data",
        description="Legislation, exchange rates and registry data of the Republic of Kazakhstan",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://github.com/AlidarXD/kz-mcp",
        log_level=settings.log_level,
    )
    law.register(server, retriever)
    resources.register(server, retriever)
    prompts.register(server)
    harden_input_schemas(server)
    return server
