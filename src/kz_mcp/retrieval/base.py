"""Retrieval port: the server depends on this protocol, never on a concrete engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kz_mcp.codes import Lang


@dataclass(frozen=True)
class RetrievedArticle:
    code: str  # Adilet document code (ngr)
    number: str
    lang: Lang
    law_title: str
    title: str
    heading: str
    url: str
    text: str
    hierarchy: tuple[str, ...] = ()
    score: float | None = None


@dataclass(frozen=True)
class IndexedCode:
    code: str
    lang: Lang
    title: str
    articles: int


@runtime_checkable
class LawRetriever(Protocol):
    """Swappable legal retrieval backend. Implementations are synchronous and may be
    CPU-heavy; the server calls them from a worker thread."""

    name: str

    def search(
        self, query: str, lang: Lang, code: str | None, top_k: int
    ) -> list[RetrievedArticle]: ...

    def get_article(self, code: str, number: str, lang: Lang) -> RetrievedArticle | None: ...

    def list_articles(self, code: str, lang: Lang) -> list[RetrievedArticle]: ...

    def list_codes(self) -> list[IndexedCode]: ...
