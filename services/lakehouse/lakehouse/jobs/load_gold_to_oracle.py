"""Gold -> Oracle: embed chunks and upsert to Oracle 23ai.

Reads lh.gold.chunks from Iceberg, embeds chunk_text via Ollama,
and upserts embeddings + metadata to Oracle chunks_embed table.

Usage:
    python -m lakehouse.jobs.load_gold_to_oracle \
        --ollama-base-url http://ollama:11434 \
        --embedding-model nomic-embed-text
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from indexer.embedders.ollama_embedder import OllamaEmbedder
from indexer.store.repository import upsert_chunks

from lakehouse.spark_session import build_spark

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


def run(
    ollama_base_url: str = "http://ollama:11434",
    embedding_model: str = "nomic-embed-text",
    embedding_dim: int = 768,
    embedding_model_version: str = "1",
    oracle_host: str = "oracle",
    oracle_port: int = 1521,
    oracle_user: str = "rag_user",
    oracle_password: str = "rag_password",
    oracle_service: str = "FREEPDB1",
    batch_size: int = 128,
    embed_timeout_seconds: int = 60,
) -> None:
    """Embed gold chunks and upsert to Oracle."""
    spark = build_spark("gold_to_oracle")
    spark.sparkContext.setLogLevel("WARN")

    try:
        # Read chunks from Iceberg gold table
        chunks_df = spark.sql("""
            SELECT
                chunk_id,
                doc_id,
                source,
                chunk_index,
                chunk_text,
                title,
                source_url,
                char_count
            FROM lh.gold.chunks
            ORDER BY doc_id, chunk_index
        """)

        count = chunks_df.count()
        log.info("load_gold.incoming_chunks", count=count)

        if count == 0:
            log.warning("load_gold.no_chunks")
            return

        # Collect rows and embed in batches
        rows = chunks_df.collect()
        log.info("load_gold.collected_rows", count=len(rows))

        # Initialize embedder
        embedder = OllamaEmbedder(
            base_url=ollama_base_url,
            model=embedding_model,
            dimension=embedding_dim,
            timeout_seconds=embed_timeout_seconds,
        )

        # Initialize Oracle connection
        import oracledb

        dsn = oracledb.makedsn(oracle_host, oracle_port, service_name=oracle_service)
        pool = oracledb.create_pool(
            user=oracle_user,
            password=oracle_password,
            dsn=dsn,
            min=2,
            max=10,
        )

        total_written = 0

        # Process chunks in batches
        for batch_idx in range(0, len(rows), batch_size):
            batch = rows[batch_idx : batch_idx + batch_size]

            # Extract texts for embedding
            texts = [row["chunk_text"] for row in batch]

            log.info(
                "load_gold.embedding_batch",
                batch_idx=batch_idx,
                batch_size=len(texts),
            )

            # Embed texts (with retry via OllamaEmbedder's internal logic)
            try:
                embeddings = embedder.embed_batch(texts)
            except Exception as e:
                log.error(
                    "load_gold.embedding_failed",
                    batch_idx=batch_idx,
                    error=str(e),
                )
                raise

            # Build upsert payloads
            upsert_rows = []
            for row, embedding in zip(batch, embeddings, strict=False):
                upsert_rows.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "doc_id": row["doc_id"],
                        "source": row["source"],
                        "chunk_index": row["chunk_index"],
                        "chunk_text": row["chunk_text"],
                        "title": row["title"],
                        "source_url": row["source_url"],
                        "char_count": row["char_count"],
                        "embedding": embedding,
                    }
                )

            # Upsert to Oracle
            try:
                n_written = upsert_chunks(
                    pool,
                    upsert_rows,
                    embedding_model=embedding_model,
                    embedding_model_ver=embedding_model_version,
                )
                total_written += n_written
                log.info(
                    "load_gold.batch_upserted",
                    batch_idx=batch_idx,
                    written=n_written,
                )
            except Exception as e:
                log.error(
                    "load_gold.upsert_failed",
                    batch_idx=batch_idx,
                    error=str(e),
                )
                raise

        embedder.close()
        pool.close()

        log.info("load_gold.done", total_written=total_written, total_chunks=count)

    finally:
        spark.stop()


if __name__ == "__main__":
    import argparse

    logging_config = structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
    )

    parser = argparse.ArgumentParser(description="Embed gold chunks to Oracle 23ai")
    parser.add_argument(
        "--ollama-base-url",
        default="http://ollama:11434",
        help="Ollama API base URL",
    )
    parser.add_argument(
        "--embedding-model",
        default="nomic-embed-text",
        help="Ollama embedding model name",
    )
    parser.add_argument("--embedding-dim", type=int, default=768, help="Embedding dimension")
    parser.add_argument(
        "--embedding-model-version",
        default="1",
        help="Embedding model version tag",
    )
    parser.add_argument("--oracle-host", default="oracle", help="Oracle hostname")
    parser.add_argument("--oracle-port", type=int, default=1521, help="Oracle port")
    parser.add_argument("--oracle-user", default="rag_user", help="Oracle user")
    parser.add_argument("--oracle-password", default="rag_password", help="Oracle password")
    parser.add_argument("--oracle-service", default="FREEPDB1", help="Oracle service name")
    parser.add_argument("--batch-size", type=int, default=128, help="Embedding batch size")
    parser.add_argument(
        "--embed-timeout-seconds",
        type=int,
        default=60,
        help="Embedding timeout in seconds",
    )

    args = parser.parse_args()
    run(
        ollama_base_url=args.ollama_base_url,
        embedding_model=args.embedding_model,
        embedding_dim=args.embedding_dim,
        embedding_model_version=args.embedding_model_version,
        oracle_host=args.oracle_host,
        oracle_port=args.oracle_port,
        oracle_user=args.oracle_user,
        oracle_password=args.oracle_password,
        oracle_service=args.oracle_service,
        batch_size=args.batch_size,
        embed_timeout_seconds=args.embed_timeout_seconds,
    )
