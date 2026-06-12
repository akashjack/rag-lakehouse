"""Contract tests for RRF fusion logic (no live Oracle needed)."""

from __future__ import annotations

from indexer.store.repository import reciprocal_rank_fusion


def _row(chunk_id: str, source: str = "kubernetes") -> dict:
    return {
        "chunk_id": chunk_id,
        "source": source,
        "doc_id": "d1",
        "chunk_index": 0,
        "title": None,
        "source_url": None,
        "distance": 0.2,
        "chunk_text_head": "sample",
    }


def test_rrf_both_lists_present() -> None:
    dense = [_row("a"), _row("b"), _row("c")]
    fts = [_row("b"), _row("a"), _row("d")]
    out = reciprocal_rank_fusion(dense, fts, k=3, rrf_k=60)
    # "a" is rank 1 in dense + rank 2 in fts -> highest combined score
    # "b" is rank 2 in dense + rank 1 in fts -> second
    ids = [r["chunk_id"] for r in out]
    assert ids[0] in ("a", "b")
    assert set(ids[:2]) == {"a", "b"}


def test_rrf_single_list_still_ranks() -> None:
    dense = [_row("x"), _row("y")]
    fts: list = []
    out = reciprocal_rank_fusion(dense, fts, k=2, rrf_k=60)
    assert len(out) == 2
    assert out[0]["chunk_id"] == "x"


def test_rrf_respects_k() -> None:
    dense = [_row(str(i)) for i in range(10)]
    fts = [_row(str(i)) for i in range(10, 20)]
    out = reciprocal_rank_fusion(dense, fts, k=3, rrf_k=60)
    assert len(out) == 3


def test_rrf_score_attached() -> None:
    dense = [_row("a")]
    fts = [_row("a")]
    out = reciprocal_rank_fusion(dense, fts, k=1, rrf_k=60)
    assert "rrf_score" in out[0]
    assert out[0]["rrf_score"] > 0
