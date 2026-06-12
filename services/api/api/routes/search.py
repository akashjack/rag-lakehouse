"""Search endpoint — dense or hybrid retrieval."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.config import get_settings

router = APIRouter()


class ChunkResult(BaseModel):
    chunk_id: str
    doc_id: str
    source: str
    chunk_index: int
    title: str | None
    source_url: str | None
    score: float
    text_head: str | None


class SearchResponse(BaseModel):
    query: str
    mode: str
    results: list[ChunkResult]


def _to_chunk_result(row: dict[str, Any], mode: str) -> ChunkResult:
    score = (
        float(row.get("rrf_score") or 0.0)
        if mode == "hybrid"
        else float(1.0 - (row.get("distance") or 0.0))
    )
    return ChunkResult(
        chunk_id=str(row.get("chunk_id") or ""),
        doc_id=str(row.get("doc_id") or ""),
        source=str(row.get("source") or ""),
        chunk_index=int(row.get("chunk_index") or 0),
        title=row.get("title"),
        source_url=row.get("source_url"),
        score=round(score, 4),
        text_head=(row.get("chunk_text_head") or "")[:300],
    )


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=20),
    mode: str = Query("hybrid", pattern="^(dense|hybrid)$"),
) -> SearchResponse:
    from indexer.config import IndexerSettings
    from indexer.embedders.ollama_embedder import OllamaEmbedder
    from indexer.store.connection import build_pool
    from indexer.store.repository import dense_search, hybrid_search

    settings = get_settings()

    # Build IndexerSettings from APISettings fields
    idx_settings = IndexerSettings(
        oracle_user=settings.oracle_user,
        oracle_dsn=settings.oracle_dsn,
        ollama_base_url=settings.ollama_base_url,
        ollama_embed_model=settings.ollama_embed_model,
        embedding_dim=settings.embedding_dim,
        embed_timeout_seconds=settings.embed_timeout_seconds,
        embedding_model_version=settings.embedding_model_version,
    )  # type: ignore[call-arg]

    try:
        with OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
            dimension=settings.embedding_dim,
            timeout_seconds=settings.embed_timeout_seconds,
        ) as embedder:
            query_vec = embedder.embed_batch([q])[0]

        pool = build_pool(idx_settings)
        try:
            if mode == "hybrid":
                rows = hybrid_search(
                    pool,
                    query_vec,
                    q,
                    k,
                    embedding_model_ver=settings.embedding_model_version,
                )
            else:
                rows = dense_search(
                    pool,
                    query_vec,
                    k,
                    embedding_model_ver=settings.embedding_model_version,
                )
        finally:
            pool.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SearchResponse(
        query=q,
        mode=mode,
        results=[_to_chunk_result(r, mode) for r in rows],
    )
