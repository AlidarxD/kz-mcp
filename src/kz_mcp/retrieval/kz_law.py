"""Adapter over `kz_law_retrieval` (BM25 + multilingual-e5 ONNX + RRF + cross-encoder)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from kz_mcp.codes import Lang
from kz_mcp.retrieval.base import IndexedCode, RetrievedArticle

_LANG: dict[str, Lang] = {"rus": "ru", "kaz": "kk"}


def _convert(article: Any) -> RetrievedArticle:
    return RetrievedArticle(
        code=article.code,
        number=article.number,
        lang=_LANG[article.language],
        law_title=article.law_title,
        title=article.title,
        heading=article.heading,
        url=article.url,
        text=article.text,
        hierarchy=tuple(article.hierarchy),
        score=None if article.score is None else float(article.score),
    )


class KzLawRetrieverAdapter:
    """Wraps a `kz_law_retrieval.Retriever`. Searches are serialized: the first one builds
    the ONNX sessions, and the reranker already uses every core."""

    def __init__(self, retriever: Any, method: str = "") -> None:
        self._retriever = retriever
        self._lock = threading.Lock()
        self.name = f"kz-law-retrieval:{method}" if method else "kz-law-retrieval"

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        method: str = "hybrid+rerank",
        embedding_model: str = "e5-base-int8",
        qdrant_url: str | None = None,
        models_cache_dir: Path | None = None,
        onnx_threads: int | None = None,
    ) -> KzLawRetrieverAdapter:
        from kz_law_retrieval import Retriever, RetrieverConfig

        config = RetrieverConfig(
            data_dir=data_dir,
            method=method,
            embedding_model=embedding_model,
            qdrant_url=qdrant_url,
            models_cache_dir=models_cache_dir,
            onnx_threads=onnx_threads,
        )
        return cls(Retriever.from_config(config), method)

    def warmup(self) -> None:
        """Load the models now instead of on the first search."""
        with self._lock:
            _ = self._retriever.searcher

    def search(
        self, query: str, lang: Lang, code: str | None, top_k: int
    ) -> list[RetrievedArticle]:
        with self._lock:
            articles = self._retriever.search(query, lang, code=code, top_k=top_k)
        return [_convert(a) for a in articles]

    def get_article(self, code: str, number: str, lang: Lang) -> RetrievedArticle | None:
        article = self._retriever.get_article(code, number, lang)
        return None if article is None else _convert(article)

    def list_articles(self, code: str, lang: Lang) -> list[RetrievedArticle]:
        return [_convert(a) for a in self._retriever.articles(code, lang)]

    def list_codes(self) -> list[IndexedCode]:
        return [
            IndexedCode(code=c.code, lang=_LANG[c.language], title=c.title, articles=c.articles)
            for c in self._retriever.codes()
        ]
