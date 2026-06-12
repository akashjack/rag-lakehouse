"""API service settings — reads from .env via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # Indexer service (called as a library, not over HTTP)
    oracle_user: str = Field(default="rag")
    oracle_password: str = Field(default="RagApp_2026", alias="ORACLE_APP_PWD")
    oracle_dsn: str = Field(default="localhost:1521/FREEPDB1")
    oracle_pool_min: int = Field(default=1)
    oracle_pool_max: int = Field(default=4)

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_embed_model: str = Field(default="nomic-embed-text")
    ollama_llm_model: str = Field(default="llama3.2:3b")
    embedding_dim: int = Field(default=768)
    embed_batch_size: int = Field(default=8)
    embed_timeout_seconds: int = Field(default=300)
    llm_timeout_seconds: int = Field(default=120)
    rag_max_context_chars: int = Field(default=6000)
    rag_top_k: int = Field(default=5)
    embedding_model_version: str = Field(default="nomic-embed-text-v1.5")
    hnsw_neighbors: int = Field(default=16, alias="HNSW_M")
    hnsw_ef_construction: int = Field(default=200)

    # Cache
    cache_ttl_seconds: int = Field(default=300)


def get_settings() -> APISettings:
    return APISettings()  # type: ignore[call-arg]
