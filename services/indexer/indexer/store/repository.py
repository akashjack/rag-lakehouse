"""Repository for chunks_embed: schema-init, upsert, dense search.

Idempotency
- init_schema(): drops & recreates by default, or skips if table exists
  with force_drop=False (default). Splits the SQL file on ';' and runs
  each statement; tolerates "already exists" errors when not dropping.
- upsert_chunks(): MERGE INTO on (chunk_id, embedding_model_ver), so
  re-embedding the same chunk with the same model is a no-op; with a
  new model_ver it inserts a new row.

Search
- dense_search(): cosine ANN via VECTOR_DISTANCE(... COSINE). Uses
  APPROX (HNSW) when the index is present; Oracle falls back to exact
  scan otherwise.
"""

from __future__ import annotations

import array
import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Sequence

    import oracledb


log = structlog.get_logger(__name__)

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

# Errors safe to swallow when init_schema is called without force_drop
_ALREADY_EXISTS_CODES = {955, 1408, 1442, 29879}  # table/index already exists, etc.


# =========================================================================
# Schema init
# =========================================================================


def _split_statements(sql_text: str) -> list[str]:
    """Crude SQL splitter — drops comments and splits on standalone ';'."""
    out: list[str] = []
    buf: list[str] = []
    for raw in sql_text.splitlines():
        line = raw.split("--", 1)[0]
        if line.strip():
            buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).rstrip().rstrip(";").strip()
            if stmt:
                out.append(stmt)
            buf = []
    return out


def init_schema(pool: oracledb.ConnectionPool, *, force_drop: bool = False) -> None:
    """Create the chunks_embed table and all its indexes.

    With force_drop=True, drops the table first (cascades to indexes).
    With force_drop=False (default), tolerates 'already exists' errors so
    init is safely re-runnable.
    """
    import oracledb

    from indexer.store.connection import acquire

    sql_text = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)

    with acquire(pool) as conn:
        cur = conn.cursor()
        if force_drop:
            try:
                cur.execute("DROP TABLE chunks_embed CASCADE CONSTRAINTS PURGE")
                log.info("oracle.schema.dropped", table="chunks_embed")
            except oracledb.DatabaseError as e:
                if e.args[0].code != 942:  # ORA-00942: table or view does not exist
                    raise

        for stmt in statements:
            try:
                cur.execute(stmt)
                log.info("oracle.schema.exec", stmt=stmt.split("\n", 1)[0][:80])
            except oracledb.DatabaseError as e:
                if e.args[0].code in _ALREADY_EXISTS_CODES:
                    log.info(
                        "oracle.schema.skip_exists",
                        stmt=stmt.split("\n", 1)[0][:80],
                        ora=e.args[0].code,
                    )
                else:
                    raise

        conn.commit()
    log.info("oracle.schema.init.done", statements=len(statements))


# =========================================================================
# Upsert
# =========================================================================

_MERGE_SQL = """
MERGE INTO chunks_embed t
USING (
    SELECT
        :chunk_id              AS chunk_id,
        :doc_id                AS doc_id,
        :source                AS source,
        :chunk_index           AS chunk_index,
        :chunk_text            AS chunk_text,
        :title                 AS title,
        :source_url            AS source_url,
        :char_count            AS char_count,
        :embedding             AS embedding,
        :embedding_model       AS embedding_model,
        :embedding_model_ver   AS embedding_model_ver
    FROM dual
) s
ON (t.chunk_id = s.chunk_id AND t.embedding_model_ver = s.embedding_model_ver)
WHEN MATCHED THEN UPDATE SET
    t.doc_id            = s.doc_id,
    t.source            = s.source,
    t.chunk_index       = s.chunk_index,
    t.chunk_text        = s.chunk_text,
    t.title             = s.title,
    t.source_url        = s.source_url,
    t.char_count        = s.char_count,
    t.embedding         = s.embedding,
    t.embedding_model   = s.embedding_model,
    t.updated_at        = CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN INSERT (
    chunk_id, doc_id, source, chunk_index, chunk_text, title, source_url,
    char_count, embedding, embedding_model, embedding_model_ver
) VALUES (
    s.chunk_id, s.doc_id, s.source, s.chunk_index, s.chunk_text, s.title,
    s.source_url, s.char_count, s.embedding, s.embedding_model,
    s.embedding_model_ver
)
"""


def _to_oracle_vector(vec: Sequence[float]) -> array.array[float]:
    """Pack a Python list[float] into the array.array('f', ...) format that
    python-oracledb expects for VECTOR(N, FLOAT32) bind variables."""
    return array.array("f", vec)


def upsert_chunks(
    pool: oracledb.ConnectionPool,
    rows: list[dict[str, object]],
    embedding_model: str,
    embedding_model_ver: str,
) -> int:
    """Upsert a batch of chunks. Returns the number of rows written.

    Each row dict must have: chunk_id, doc_id, source, chunk_index,
    chunk_text, embedding (list[float]). title, source_url, char_count
    are optional.
    """
    from indexer.store.connection import acquire

    if not rows:
        return 0

    binds = []
    for r in rows:
        binds.append(
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "source": r["source"],
                "chunk_index": r["chunk_index"],
                "chunk_text": r["chunk_text"],
                "title": r.get("title"),
                "source_url": r.get("source_url"),
                "char_count": r.get("char_count"),
                "embedding": _to_oracle_vector(r["embedding"]),  # type: ignore[arg-type]
                "embedding_model": embedding_model,
                "embedding_model_ver": embedding_model_ver,
            }
        )

    with acquire(pool) as conn:
        cur = conn.cursor()
        cur.executemany(_MERGE_SQL, binds)
        conn.commit()
    log.info(
        "oracle.upsert",
        rows=len(rows),
        model=embedding_model,
        model_ver=embedding_model_ver,
    )
    return len(rows)


# =========================================================================
# Dense search
# =========================================================================

_DENSE_SEARCH_SQL = """
SELECT
    chunk_id,
    doc_id,
    source,
    chunk_index,
    title,
    source_url,
    VECTOR_DISTANCE(embedding, :qvec, COSINE) AS distance,
    DBMS_LOB.SUBSTR(chunk_text, 4000, 1) AS chunk_text_head
FROM chunks_embed
WHERE embedding_model_ver = :model_ver
ORDER BY distance
FETCH APPROX FIRST :k ROWS ONLY WITH TARGET ACCURACY 95
"""


def dense_search(
    pool: oracledb.ConnectionPool,
    query_vector: Sequence[float],
    k: int,
    embedding_model_ver: str,
) -> list[dict[str, object]]:
    """Cosine ANN search via HNSW. Returns top-k rows sorted by distance ascending."""
    from indexer.store.connection import acquire

    qvec = _to_oracle_vector(query_vector)
    with acquire(pool) as conn:
        cur = conn.cursor()
        cur.execute(
            _DENSE_SEARCH_SQL,
            qvec=qvec,
            model_ver=embedding_model_ver,
            k=k,
        )
        cols = [d[0].lower() for d in cur.description]
        out = [dict(zip(cols, row, strict=True)) for row in cur]
    log.info("oracle.dense_search", k=k, returned=len(out))
    return out


# =========================================================================
# Stats
# =========================================================================


def count_rows(pool: oracledb.ConnectionPool) -> dict[str, int]:
    """Return total + per-model row counts. Useful for the CLI 'stats' command."""
    import oracledb

    from indexer.store.connection import acquire

    with acquire(pool) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT embedding_model_ver, COUNT(*) "
                "FROM chunks_embed GROUP BY embedding_model_ver"
            )
            rows = cur.fetchall()
        except oracledb.DatabaseError as e:
            if e.args[0].code == 942:  # ORA-00942: table doesn't exist yet
                return {"_total": 0}
            raise
    out: dict[str, int] = {"_total": 0}
    for model_ver, count in rows:
        out[model_ver] = count
        out["_total"] += count
    return out


# =========================================================================
# HNSW index lifecycle
# =========================================================================


def drop_vector_index(pool: oracledb.ConnectionPool) -> None:
    """Drop the HNSW vector index so DML is allowed.

    Oracle's INMEMORY NEIGHBOR GRAPH index does not support concurrent DML
    (ORA-51928). Drop before bulk upsert, rebuild after.
    """
    import oracledb

    from indexer.store.connection import acquire

    with acquire(pool) as conn:
        cur = conn.cursor()
        try:
            cur.execute("DROP INDEX chunks_embed_hnsw_idx")
            conn.commit()
            log.info("oracle.vector_index.dropped")
        except oracledb.DatabaseError as e:
            if e.args[0].code == 1418:  # ORA-01418: index does not exist
                log.info("oracle.vector_index.not_found_skip")
            else:
                raise


def rebuild_vector_index(pool: oracledb.ConnectionPool, settings: object) -> None:
    """Rebuild the HNSW vector index after bulk load."""
    from indexer.store.connection import acquire

    m = getattr(settings, "hnsw_neighbors", 16)
    ef = getattr(settings, "hnsw_ef_construction", 200)
    sql = f"""
        CREATE VECTOR INDEX chunks_embed_hnsw_idx
            ON chunks_embed (embedding)
            ORGANIZATION INMEMORY NEIGHBOR GRAPH
            DISTANCE COSINE
            WITH TARGET ACCURACY 95
            PARAMETERS (TYPE HNSW, NEIGHBORS {m}, EFCONSTRUCTION {ef})
    """
    with acquire(pool) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    log.info("oracle.vector_index.rebuilt", neighbors=m, ef_construction=ef)


# =========================================================================
# Full-text search (Oracle Text CONTEXT index)
# =========================================================================

# Oracle Text CONTAINS operator chars that cause DRG-50901 parse errors when
# present in raw natural-language queries. Strip them; they carry no meaning for
# keyword retrieval (? is a fuzzy-operator prefix, & is AND, | is OR, etc.).
_ORA_TEXT_SPECIAL = re.compile(r"[&|!(){}\[\]*?,;:\"'\\]")


# Oracle Text default stoplist (English) — these are silently ignored by
# the CONTEXT index. Including them in an AND query produces zero results
# because the index has no entries for them.
_ORA_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "not",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "is",
        "it",
        "be",
        "as",
        "by",
        "we",
        "he",
        "she",
        "they",
        "are",
        "was",
        "were",
        "with",
        "this",
        "that",
        "from",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "but",
        "what",
        "which",
        "who",
        "how",
        "when",
        "where",
        "why",
        "can",
        "will",
        "would",
        "there",
        "been",
        "being",
    }
)


def _sanitize_fts_query(text: str) -> str:
    """Convert a plain text query to an Oracle Text CONTAINS expression.

    1. Strip Oracle Text special characters.
    2. Split into words.
    3. Drop English stopwords (Oracle Text ignores them; including them
       in an AND query silently reduces results to near-zero).
    4. AND-join remaining terms so CONTAINS finds chunks with ALL terms.

    Falls back to the cleaned raw text if no meaningful terms remain
    (e.g. a query that is entirely stopwords).
    """
    cleaned = _ORA_TEXT_SPECIAL.sub(" ", text).strip()
    terms = [w.lower() for w in cleaned.split() if w.lower() not in _ORA_STOPWORDS and len(w) > 1]
    if not terms:
        return cleaned
    return " AND ".join(terms)


_FTS_SEARCH_SQL = """
SELECT
    chunk_id,
    doc_id,
    source,
    chunk_index,
    title,
    source_url,
    SCORE(1)                                      AS fts_score,
    DBMS_LOB.SUBSTR(chunk_text, 4000, 1)          AS chunk_text_head
FROM chunks_embed
WHERE CONTAINS(chunk_text, :query_text, 1) > 0
  AND embedding_model_ver = :model_ver
ORDER BY fts_score DESC
FETCH FIRST :k ROWS ONLY
"""


def fts_search(
    pool: oracledb.ConnectionPool,
    query_text: str,
    k: int,
    embedding_model_ver: str,
) -> list[dict[str, object]]:
    """Oracle Text CONTAINS search. Returns top-k by FTS relevance score (descending)."""
    from indexer.store.connection import acquire

    oracle_query = _sanitize_fts_query(query_text)
    if not oracle_query.strip():
        log.info("oracle.fts_search.skipped", reason="empty_query_after_sanitize")
        return []
    with acquire(pool) as conn:
        cur = conn.cursor()
        cur.execute(
            _FTS_SEARCH_SQL,
            query_text=oracle_query,
            model_ver=embedding_model_ver,
            k=k,
        )
        cols = [d[0].lower() for d in cur.description]
        out = [dict(zip(cols, row, strict=True)) for row in cur]
    log.info("oracle.fts_search", k=k, returned=len(out))
    return out


# =========================================================================
# Reciprocal Rank Fusion
# =========================================================================


def reciprocal_rank_fusion(
    dense_results: list[dict[str, object]],
    fts_results: list[dict[str, object]],
    k: int = 5,
    rrf_k: int = 60,
) -> list[dict[str, object]]:
    """Fuse dense (ANN) and sparse (FTS) result lists via RRF.

    RRF score = 1/(rrf_k + rank_dense) + 1/(rrf_k + rank_fts)

    rrf_k=60 is the standard value from the original RRF paper
    (Cormack et al. 2009). Higher values smooth the influence of
    top-ranked results; lower values amplify them.
    """
    scores: dict[str, float] = {}
    meta: dict[str, dict[str, object]] = {}

    for rank, row in enumerate(dense_results, start=1):
        cid = str(row["chunk_id"])
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        meta[cid] = row

    for rank, row in enumerate(fts_results, start=1):
        cid = str(row["chunk_id"])
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        if cid not in meta:
            meta[cid] = row

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]

    results = []
    for rank, (cid, score) in enumerate(ranked, start=1):
        row = dict(meta[cid])
        row["rrf_score"] = round(score, 6)
        row["rrf_rank"] = rank
        results.append(row)

    log.info(
        "oracle.rrf",
        dense_in=len(dense_results),
        fts_in=len(fts_results),
        out=len(results),
    )
    return results


def hybrid_search(
    pool: oracledb.ConnectionPool,
    query_vector: Sequence[float],
    query_text: str,
    k: int,
    embedding_model_ver: str,
    rrf_k: int = 60,
    fetch: int = 20,
) -> list[dict[str, object]]:
    """Dense ANN + Oracle Text FTS fused via RRF.

    fetch: how many candidates to retrieve from each sub-search before fusion.
    Set fetch >= 2*k to ensure good recall after fusion.
    """
    dense = dense_search(pool, query_vector, fetch, embedding_model_ver)
    fts = fts_search(pool, query_text, fetch, embedding_model_ver)
    return reciprocal_rank_fusion(dense, fts, k=k, rrf_k=rrf_k)
