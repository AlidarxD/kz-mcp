"""Runtime configuration from environment variables (prefix KZ_MCP_) or a local .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KZ_MCP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Legal retrieval
    retriever: Literal["auto", "kz-law", "fixture"] = Field(
        "auto",
        description="auto: kz-law when its index is available, otherwise the bundled fixture",
    )
    law_data_dir: Path | None = Field(
        None, description="kz-law-llm data directory (chunks/ and qdrant/)"
    )
    law_method: Literal[
        "bm25", "dense", "hybrid", "bm25+rerank", "dense+rerank", "hybrid+rerank"
    ] = "hybrid+rerank"
    law_embedding_model: str = "e5-base-int8"
    law_qdrant_url: str | None = None
    law_models_cache_dir: Path | None = None
    law_onnx_threads: int | None = None
    law_warmup: bool = Field(False, description="Load retrieval models at startup")

    # Upstream HTTP
    http_timeout_s: float = Field(10.0, gt=0, le=60)
    http_connect_timeout_s: float = Field(5.0, gt=0, le=30)
    http_retries: int = Field(3, ge=1, le=6, description="Attempts per upstream request")
    offline: bool = Field(False, description="Serve bundled snapshots only, no network")

    # Cache
    redis_url: str | None = Field(None, description="redis://…; in-process cache if unset")
    cache_prefix: str = "kzmcp:"
    rates_ttl_s: int = Field(3600, description="Today's and tomorrow's rates")
    rates_history_ttl_s: int = Field(30 * 86400, description="Rates of past days")
    company_ttl_s: int = 86400
    stale_ttl_s: int = Field(7 * 86400, description="Last good copy kept for outages")
