"""Silver -> Gold: chunk documents into retrieval-ready windows.

1500-char chunks with 200-char overlap. Phase 4 swaps in token-aware
chunking once the embedding model is locked.
"""

from __future__ import annotations

from typing import TypedDict

import structlog
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from lakehouse.spark_session import build_spark

log = structlog.get_logger(__name__)


CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


class Chunk(TypedDict):
    chunk_index: int
    text: str
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[Chunk] = []
    buf = ""
    start = 0
    pos = 0

    for para in paragraphs:
        candidate = (buf + "\n\n" + para).strip() if buf else para
        if len(candidate) <= size:
            buf = candidate
            continue
        if buf:
            out.append(
                {
                    "chunk_index": len(out),
                    "text": buf,
                    "start_char": start,
                    "end_char": start + len(buf),
                }
            )
            start = max(0, start + len(buf) - overlap)
        if len(para) > size:
            i = 0
            while i < len(para):
                window = para[i : i + size]
                out.append(
                    {
                        "chunk_index": len(out),
                        "text": window,
                        "start_char": pos + i,
                        "end_char": pos + i + len(window),
                    }
                )
                i += size - overlap
            buf = ""
        else:
            buf = para
        pos += len(para) + 2

    if buf:
        out.append(
            {
                "chunk_index": len(out),
                "text": buf,
                "start_char": start,
                "end_char": start + len(buf),
            }
        )

    return out


CHUNK_OUT_SCHEMA = ArrayType(
    StructType(
        [
            StructField("chunk_index", IntegerType()),
            StructField("text", StringType()),
            StructField("start_char", IntegerType()),
            StructField("end_char", IntegerType()),
        ]
    )
)


def run() -> None:
    spark = build_spark("silver_to_gold")
    spark.sparkContext.setLogLevel("WARN")

    spark.sql("CREATE NAMESPACE IF NOT EXISTS lh.gold")

    spark.sql("""
        CREATE TABLE IF NOT EXISTS lh.gold.chunks (
            chunk_id      STRING,
            doc_id        STRING,
            doc_id_prefix STRING,
            source        STRING,
            source_url    STRING,
            title         STRING,
            chunk_index   INT,
            text          STRING,
            char_count    INT,
            start_char    INT,
            end_char      INT,
            chunked_at    TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (source, doc_id_prefix)
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'zstd',
            'format-version' = '2'
        )
    """)

    chunk_udf = F.udf(chunk_text, CHUNK_OUT_SCHEMA)

    src = spark.sql("""
        SELECT doc_id, source, source_url, title, text
        FROM lh.silver.documents
        WHERE text IS NOT NULL AND char_count >= 500
    """)

    log.info("silver_to_gold.incoming_docs", docs=src.count())

    exploded = (
        src.withColumn("chunks", chunk_udf(F.col("text")))
        .withColumn("chunk", F.explode("chunks"))
        .select(
            F.concat_ws("::", F.col("doc_id"), F.col("chunk.chunk_index").cast("string")).alias(
                "chunk_id"
            ),
            F.col("doc_id"),
            F.substring("doc_id", 1, 2).alias("doc_id_prefix"),
            F.col("source"),
            F.col("source_url"),
            F.col("title"),
            F.col("chunk.chunk_index").alias("chunk_index"),
            F.col("chunk.text").alias("text"),
            F.length(F.col("chunk.text")).alias("char_count"),
            F.col("chunk.start_char").alias("start_char"),
            F.col("chunk.end_char").alias("end_char"),
            F.current_timestamp().alias("chunked_at"),
        )
    )

    exploded.createOrReplaceTempView("incoming_chunks")

    spark.sql("""
        MERGE INTO lh.gold.chunks t
        USING incoming_chunks s
        ON t.chunk_id = s.chunk_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    final_row = spark.sql("SELECT COUNT(*) AS n FROM lh.gold.chunks").first()

    final = final_row["n"] if final_row is not None else 0

    avg_row = spark.sql("""
        SELECT AVG(c) AS avg_chunks_per_doc FROM (
             SELECT COUNT(*) AS c FROM lh.gold.chunks GROUP BY doc_id
        )
    """).first()

    avg = avg_row["avg_chunks_per_doc"] if avg_row is not None else 0
    log.info("silver_to_gold.done", chunks_total=final, avg_per_doc=float(avg or 0))

    spark.stop()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level="INFO")
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    run()
