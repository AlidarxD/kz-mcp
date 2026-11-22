"""Legal retrieval behind the `LawRetriever` port."""

from __future__ import annotations

import importlib.util
import logging

from kz_mcp.retrieval.base import IndexedCode, LawRetriever, RetrievedArticle
from kz_mcp.retrieval.fixture import FixtureRetriever
from kz_mcp.settings import Settings

__all__ = ["FixtureRetriever", "IndexedCode", "LawRetriever", "RetrievedArticle", "build_retriever"]

log = logging.getLogger(__name__)


def _kz_law_available(settings: Settings) -> str | None:
    """None if the kz-law backend can be used, otherwise the reason it cannot."""
    if importlib.util.find_spec("kz_law_retrieval") is None:
        return "package kz-law-retrieval is not installed (pip extra `law`)"
    if settings.law_data_dir is None:
        return "KZ_MCP_LAW_DATA_DIR is not set"
    if not (settings.law_data_dir / "chunks").is_dir():
        return f"no chunks/ directory in {settings.law_data_dir}"
    return None


def build_retriever(settings: Settings) -> LawRetriever:
    if settings.retriever != "fixture":
        problem = _kz_law_available(settings)
        if problem is None:
            from kz_mcp.retrieval.kz_law import KzLawRetrieverAdapter

            assert settings.law_data_dir is not None  # noqa: S101 - checked above
            adapter = KzLawRetrieverAdapter.from_data_dir(
                settings.law_data_dir,
                method=settings.law_method,
                embedding_model=settings.law_embedding_model,
                qdrant_url=settings.law_qdrant_url,
                models_cache_dir=settings.law_models_cache_dir,
                onnx_threads=settings.law_onnx_threads,
            )
            if settings.law_warmup:
                adapter.warmup()
            log.info("legal retrieval: %s", adapter.name)
            return adapter
        if settings.retriever == "kz-law":
            raise RuntimeError(f"KZ_MCP_RETRIEVER=kz-law but {problem}")
        log.warning("legal retrieval: bundled fixture (%s)", problem)
    return FixtureRetriever()
