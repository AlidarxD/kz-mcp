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
