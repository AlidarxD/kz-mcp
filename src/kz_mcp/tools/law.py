"""Legal tools: `search_law` and `get_law_article`."""

from __future__ import annotations

from functools import partial
from typing import Annotated

import anyio.to_thread
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from kz_mcp.codes import CodeName, Lang, citation_id, code_by_ngr, resolve_code
from kz_mcp.models.law import LawArticle, LawArticleHit, SearchLawResult
from kz_mcp.retrieval.base import LawRetriever, RetrievedArticle

SNIPPET_CHARS = 400
SOURCE = "adilet.zan.kz (official legal information system of the Republic of Kazakhstan)"

# Local index only: no side effects, same answer for the same index, no outside world.
LOCAL_READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

Query = Annotated[
    str,
    Field(
        min_length=2,
        max_length=500,
        description="Question or keywords in Russian or Kazakh, e.g. 'сколько дней отпуска'",
    ),
]
LangArg = Annotated[Lang, Field(description="Language of the query and of the returned text")]
CodeArg = Annotated[
    CodeName,
    Field(description="Legal act: an alias (labour, tax, …) or an Adilet document code"),
]
ArticleNumber = Annotated[
    str,
    Field(
        min_length=1,
        max_length=20,
        pattern=r"^[0-9]+(-[0-9]+)*$|^Преамбула$",
        description="Article number as written in the act, e.g. '88' or '18-1'",
    ),
]


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text.rfind(" ", 0, SNIPPET_CHARS)
    return text[: cut if cut > SNIPPET_CHARS // 2 else SNIPPET_CHARS] + " …"


def _alias(ngr: str) -> str | None:
    code = code_by_ngr(ngr)
    return code.alias if code else None


def to_hit(a: RetrievedArticle) -> LawArticleHit:
    return LawArticleHit(
        citation_id=citation_id(a.code, a.lang, a.number),
        code=a.code,
        code_alias=_alias(a.code),
        law_title=a.law_title,
        article_number=a.number,
        title=a.title,
        heading=a.heading,
        snippet=_snippet(a.text),
        url=a.url,
        score=a.score,
    )


def to_article(a: RetrievedArticle) -> LawArticle:
    return LawArticle(
        citation_id=citation_id(a.code, a.lang, a.number),
        code=a.code,
        code_alias=_alias(a.code),
        law_title=a.law_title,
        article_number=a.number,
        title=a.title,
        heading=a.heading,
        hierarchy=list(a.hierarchy),
        lang=a.lang,
        text=a.text,
        url=a.url,
        source=SOURCE,
    )


def register(server: MCPServer, retriever: LawRetriever) -> None:
    @server.tool(
        title="Search Kazakhstan legislation",
        annotations=LOCAL_READ_ONLY,
    )
    async def search_law(
        query: Query,
        lang: LangArg = "ru",
        code: Annotated[
            CodeName | None, Field(description="Restrict the search to one legal act")
        ] = None,
        top_k: Annotated[int, Field(ge=1, le=20, description="Number of articles")] = 5,
    ) -> SearchLawResult:
        """Find the articles of Kazakhstan's codes (Constitution, Civil, Labour, Tax,
        Criminal, Administrative Offences) that answer a question, in Russian or Kazakh.

        Hybrid search (BM25 + multilingual embeddings, reranked by a cross-encoder) over the
        current editions from adilet.zan.kz. Returns snippets; call get_law_article for the
        full text, and cite articles by citation_id and url. Not legal advice."""
        ngr = resolve_code(code).ngr if code else None
        found = await anyio.to_thread.run_sync(
            partial(retriever.search, query.strip(), lang, ngr, top_k)
        )
        return SearchLawResult(
            query=query,
            lang=lang,
            code=ngr,
            retriever=retriever.name,
            results=[to_hit(a) for a in found],
        )

    @server.tool(
        title="Get an article of Kazakhstan legislation",
        annotations=LOCAL_READ_ONLY,
    )
    async def get_law_article(
        code: CodeArg,
        article_number: ArticleNumber,
        lang: LangArg = "ru",
    ) -> LawArticle:
        """Full current text of one article of a Kazakhstan code, with a stable citation id
        and a link to adilet.zan.kz."""
        law = resolve_code(code)
        article = await anyio.to_thread.run_sync(
            partial(retriever.get_article, law.ngr, article_number, lang)
        )
        if article is None:
            raise ToolError(
                f"Article {article_number} of the {law.name_en} ({lang}) is not in the index; "
                "it may not exist or may be repealed. Use search_law to find the right article."
            )
        return to_article(article)
