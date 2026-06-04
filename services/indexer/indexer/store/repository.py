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
from pathlib import Path
from typing import TYPE_CHECKING

import oracledb
import structlog

from indexer.store.connection import acquire

if TYPE_CHECKING:
    from collections.abc import Sequence


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
