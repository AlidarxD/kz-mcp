"""Legal acts exposed as MCP resources: the list of codes and each code's table of contents."""

from __future__ import annotations

import json
from typing import get_args

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError

from kz_mcp.codes import Lang, citation_id, code_by_ngr, resolve_code
from kz_mcp.models.law import LawCodeInfo
from kz_mcp.retrieval.base import LawRetriever

CODES_URI = "kzlaw://codes"
TOC_URI = "kzlaw://codes/{code}/{lang}"


def register(server: MCPServer, retriever: LawRetriever) -> None:
    @server.resource(
        CODES_URI,
        name="law_codes",
        title="Indexed legal acts",
        description="Legal acts of Kazakhstan available to search_law, per language",
        mime_type="application/json",
    )
    def law_codes() -> str:
        infos = []
        for c in retriever.list_codes():
            known = code_by_ngr(c.code)
            infos.append(
                LawCodeInfo(
                    code=c.code,
                    alias=known.alias if known else None,
                    name_en=known.name_en if known else None,
                    lang=c.lang,
                    title=c.title,
                    articles=c.articles,
                ).model_dump()
            )
        return json.dumps(infos, ensure_ascii=False)

    @server.resource(
        TOC_URI,
        name="law_code_contents",
        title="Table of contents of a legal act",
        description="Article numbers, headings and citation ids of one act in one language "
        "(code: alias or Adilet code; lang: ru|kk)",
        mime_type="application/json",
    )
    def law_code_contents(code: str, lang: str) -> str:
        if lang not in get_args(Lang):
            raise ResourceError("lang must be ru or kk")
        try:
            law = resolve_code(code)
        except ValueError as exc:
            raise ResourceError(str(exc)) from None
        language: Lang = "ru" if lang == "ru" else "kk"
        articles = retriever.list_articles(law.ngr, language)
        return json.dumps(
            {
                "code": law.ngr,
                "alias": law.alias,
                "lang": language,
                "title": articles[0].law_title if articles else law.name_en,
                "url": law.url(language),
                "articles": [
                    {
                        "number": a.number,
                        "heading": a.heading,
                        "citation_id": citation_id(a.code, language, a.number),
                    }
                    for a in articles
                ],
            },
            ensure_ascii=False,
        )
