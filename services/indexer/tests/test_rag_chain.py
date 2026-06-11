"""Contract tests for RAG chain logic (no live LLM or Oracle)."""

from __future__ import annotations

from indexer.rag_chain import _build_context, build_citations


def _chunk(i: int, text: str = "sample text") -> dict:
    return {
        "chunk_id": f"c{i}",
        "doc_id": f"d{i}",
        "source": "kubernetes",
        "chunk_index": i,
        "title": f"Title {i}",
        "source_url": f"https://example.com/{i}",
        "chunk_text_head": text,
        "distance": 0.2,
    }


def test_build_context_respects_max_chars() -> None:
    chunks = [_chunk(i, "x" * 1000) for i in range(10)]
    context, used = _build_context(chunks, max_chars=3000)
    assert len(context) <= 3500
    assert len(used) < 10


def test_build_context_includes_title_and_source() -> None:
    chunks = [_chunk(1, "pod is a unit")]
    context, _ = _build_context(chunks, max_chars=5000)
    assert "Title 1" in context
    assert "kubernetes" in context


def test_build_citations_matches_used_chunks() -> None:
    chunks = [_chunk(i, "x" * 100) for i in range(5)]
    citations = build_citations(chunks, max_chars=10000)
    assert len(citations) == 5
    assert citations[0]["number"] == 1
    assert citations[0]["source"] == "kubernetes"


def test_build_citations_truncated_by_max_chars() -> None:
    chunks = [_chunk(i, "x" * 2000) for i in range(10)]
    citations = build_citations(chunks, max_chars=3000)
    assert len(citations) < 10
