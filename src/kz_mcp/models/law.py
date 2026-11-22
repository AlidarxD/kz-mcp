from __future__ import annotations

from pydantic import Field

from kz_mcp.codes import Lang
from kz_mcp.models import StrictModel


class LawArticleHit(StrictModel):
    citation_id: str = Field(description="Stable id to cite, e.g. kz-law:K1500000414:ru:88")
    code: str = Field(description="Adilet document code")
    code_alias: str | None = Field(description="Short alias of the act, e.g. labour")
    law_title: str
    article_number: str
    title: str
    heading: str
    snippet: str = Field(description="Beginning of the article text")
    url: str = Field(description="Link to the article on adilet.zan.kz")
    score: float | None = Field(description="Retrieval score; comparable within one result")


class SearchLawResult(StrictModel):
    query: str
    lang: Lang
    code: str | None
    retriever: str = Field(description="Backend that produced the results")
    results: list[LawArticleHit]


class LawArticle(StrictModel):
    citation_id: str
    code: str
    code_alias: str | None
    law_title: str
    article_number: str
    title: str
    heading: str
    hierarchy: list[str] = Field(description="Part › section › chapter of the act")
    lang: Lang
    text: str = Field(description="Full current text of the article")
    url: str
    source: str = Field(description="Where the text comes from")


class LawCodeInfo(StrictModel):
    code: str
    alias: str | None
    name_en: str | None
    lang: Lang
    title: str
    articles: int = Field(description="Indexed articles")
