"""RAG chain: hybrid retrieval + LLM generation with source citations."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import structlog
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM

from indexer.config import IndexerSettings

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

_PROMPT_TEMPLATE = """You are a precise technical assistant. Answer the question \
using ONLY the provided context chunks. If the answer is not in the context, say \
"I don't have enough information in the provided context to answer that." \
Do not make up facts. Be concise. Use bullet points for multi-part answers.

Context chunks (in retrieval order):

{context}

---

Question: {question}

Answer:"""


def _build_context(chunks: list[dict], max_chars: int) -> tuple[str, list[dict]]:
    """Stuff chunks into the context window up to max_chars."""
    parts: list[str] = []
    used: list[dict] = []
    total = 0

    for i, chunk in enumerate(chunks, start=1):
        text = chunk.get("chunk_text_head") or ""
        title = chunk.get("title") or ""
        source = chunk.get("source") or ""
        url = chunk.get("source_url") or ""

        header = f"[{i}] {title} ({source})"
        if url:
            header += f" -- {url}"
        block = f"{header}\n{text}"

        if total + len(block) > max_chars:
            break

        parts.append(block)
        used.append(chunk)
        total += len(block)

    return "\n\n".join(parts), used


def build_rag_chain(settings: IndexerSettings):
    """Build a streaming LCEL RAG chain using Ollama LLM."""
    llm = OllamaLLM(
        model=settings.ollama_llm_model,
        base_url=settings.ollama_base_url,
        timeout=settings.llm_timeout_seconds,
        temperature=0.1,
    )
    prompt = PromptTemplate.from_template(_PROMPT_TEMPLATE)
    return prompt | llm | StrOutputParser()


def ask(
    settings: IndexerSettings,
    chunks: list[dict],
    question: str,
) -> Iterator[str]:
    """Stream an answer token-by-token given retrieved chunks and a question."""
    context, used_chunks = _build_context(chunks, settings.rag_max_context_chars)

    if not context.strip():
        yield "No relevant context found. Try broadening your query."
        return

    log.info(
        "rag.ask",
        chunks_available=len(chunks),
        chunks_used=len(used_chunks),
        context_chars=len(context),
        model=settings.ollama_llm_model,
    )

    chain = build_rag_chain(settings)
    yield from chain.stream({"context": context, "question": question})


def build_citations(chunks: list[dict], max_chars: int) -> list[dict]:
    """Build citation list for the chunks that fit in the context window."""
    _, used = _build_context(chunks, max_chars)
    return [
        {
            "number": i,
            "title": chunk.get("title") or "",
            "source": chunk.get("source") or "",
            "source_url": chunk.get("source_url") or "",
            "doc_id": chunk.get("doc_id") or "",
            "chunk_index": chunk.get("chunk_index"),
        }
        for i, chunk in enumerate(used, start=1)
    ]
