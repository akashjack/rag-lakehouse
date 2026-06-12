"""Ask endpoint — SSE streaming LLM answer."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    k: int = 5
    mode: str = "hybrid"


def _event(data: str, event: str = "token") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/ask")
def ask_stream(req: AskRequest) -> StreamingResponse:
    from indexer.config import IndexerSettings
    from indexer.embedders.ollama_embedder import OllamaEmbedder
    from indexer.rag_chain import ask, build_citations
    from indexer.store.connection import build_pool
    from indexer.store.repository import dense_search, hybrid_search

    from api.config import get_settings

    settings = get_settings()
    idx_settings = IndexerSettings(
        oracle_user=settings.oracle_user,
        oracle_dsn=settings.oracle_dsn,
        ollama_base_url=settings.ollama_base_url,
        ollama_embed_model=settings.ollama_embed_model,
        ollama_llm_model=settings.ollama_llm_model,
        embedding_dim=settings.embedding_dim,
        embed_timeout_seconds=settings.embed_timeout_seconds,
        llm_timeout_seconds=settings.llm_timeout_seconds,
        rag_max_context_chars=settings.rag_max_context_chars,
        rag_top_k=settings.rag_top_k,
        embedding_model_version=settings.embedding_model_version,
    )  # type: ignore[call-arg]

    def generate():
        try:
            with OllamaEmbedder(
                base_url=settings.ollama_base_url,
                model=settings.ollama_embed_model,
                dimension=settings.embedding_dim,
                timeout_seconds=settings.embed_timeout_seconds,
            ) as embedder:
                query_vec = embedder.embed_batch([req.question])[0]

            pool = build_pool(idx_settings)
            try:
                if req.mode == "hybrid":
                    chunks = hybrid_search(
                        pool,
                        query_vec,
                        req.question,
                        req.k,
                        embedding_model_ver=settings.embedding_model_version,
                    )
                else:
                    chunks = dense_search(
                        pool,
                        query_vec,
                        req.k,
                        embedding_model_ver=settings.embedding_model_version,
                    )
            finally:
                pool.close()

            for token in ask(idx_settings, chunks, req.question):
                yield _event(token, "token")

            citations = build_citations(chunks, settings.rag_max_context_chars)
            yield _event(json.dumps(citations), "citations")
            yield _event("done", "done")

        except Exception as e:
            yield _event(str(e), "error")

    return StreamingResponse(generate(), media_type="text/event-stream")
