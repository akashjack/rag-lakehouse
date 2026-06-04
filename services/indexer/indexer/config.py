"""Indexer settings — env-driven via pydantic-settings.

Two URL knobs for Ollama because the embed job runs in two contexts:
- CLI on the host  → http://localhost:11434
- Spark container  → http://ollama:11434  (via ragnet DNS)

The DEFAULT here is the in-network URL because the production-shaped
use case (the embed job) needs that. CLI smoke tests on the host can
override with OLLAMA_BASE_URL=http://localhost:11434.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndexerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === Ollama ===
    ollama_base_url: str = Field(default="http://ollama:11434")
    ollama_embed_model: str = Field(default="nomic-embed-text")
    embedding_dim: int = Field(default=768)
    embed_batch_size: int = Field(default=32)
    embed_timeout_seconds: int = Field(default=60)

    # === Oracle ===
    oracle_user: str = Field(default="rag")
    oracle_password: str = Field(default="RagApp_2026", alias="ORACLE_APP_PWD")
    oracle_dsn: str = Field(default="localhost:1521/FREEPDB1")
    oracle_pool_min: int = Field(default=1)
    oracle_pool_max: int = Field(default=4)

    # === Vector index tuning (HNSW) ===
    hnsw_neighbors: int = Field(default=16, alias="HNSW_M")
    hnsw_ef_construction: int = Field(default=200)

    # === Behaviour ===
    embedding_model_version: str = Field(default="nomic-embed-text-v1.5")
    # Used in MERGE keys — re-running embed with a new value re-embeds rows.


def get_settings() -> IndexerSettings:
    return IndexerSettings()  # type: ignore[call-arg]
