"""Corpus expansion loader.

Reads markdown files from services/corpus/, chunks them,
embeds via Ollama, and upserts to Oracle chunks_embed table.
Idempotent — safe to re-run.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import structlog

sys.path.insert(0, "services/indexer")

from indexer.config import IndexerSettings
from indexer.embedders.ollama_embedder import OllamaEmbedder
from indexer.store.connection import build_pool
from indexer.store.repository import (
    drop_vector_index,
    rebuild_vector_index,
    upsert_chunks,
)

log = structlog.get_logger(__name__)

CORPUS_DIR = Path(__file__).parent.parent / "services" / "corpus"
CHUNK_SIZE = 800  # chars per chunk
CHUNK_OVERLAP = 100


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple character-level sliding window chunker."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start += size - overlap
    return [c for c in chunks if len(c) > 50]


def make_doc_id(source: str, filename: str) -> str:
    return hashlib.md5(f"{source}::{filename}".encode()).hexdigest()


def load_corpus(corpus_dir: Path, settings: IndexerSettings) -> list[dict]:
    """Read all markdown files and return chunk rows ready for upsert."""
    rows = []
    for md_file in sorted(corpus_dir.rglob("*.md")):
        source = md_file.parent.name  # kafka | react-native
        text = md_file.read_text()
        title = text.splitlines()[0].lstrip("# ").strip() if text else md_file.stem
        doc_id = make_doc_id(source, md_file.name)

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}::{i}"
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "source": source,
                    "chunk_index": i,
                    "chunk_text": chunk,
                    "title": title,
                    "source_url": None,
                    "char_count": len(chunk),
                    "embedding": None,  # filled below
                }
            )
        log.info("corpus.loaded", file=md_file.name, source=source, chunks=len(chunks))
    return rows


def main() -> int:
    settings = IndexerSettings(
        oracle_dsn="localhost:1521/FREEPDB1",
        oracle_user="rag",
        oracle_password="RagApp_2026",
        ollama_base_url="http://localhost:11434",
    )  # type: ignore[call-arg]

    corpus_dir = Path(__file__).parent.parent / "services" / "corpus"
    rows = load_corpus(corpus_dir, settings)
    log.info("corpus.total_chunks", count=len(rows))

    pool = build_pool(settings)

    # Drop HNSW index before DML
    drop_vector_index(pool)

    with OllamaEmbedder(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
        dimension=settings.embedding_dim,
        timeout_seconds=settings.embed_timeout_seconds,
    ) as embedder:
        batch_size = settings.embed_batch_size
        total_written = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            texts = [r["chunk_text"] for r in batch]
            vectors = embedder.embed_batch(texts)

            upsert_rows = []
            for row, vec in zip(batch, vectors, strict=True):
                upsert_rows.append({**row, "embedding": vec})

            written = upsert_chunks(
                pool,
                upsert_rows,
                embedding_model=settings.ollama_embed_model,
                embedding_model_ver=settings.embedding_model_version,
            )
            total_written += written
            log.info("corpus.batch_done", batch=i // batch_size + 1, total=total_written)

    # Rebuild HNSW index
    rebuild_vector_index(pool, settings)
    pool.close()

    log.info("corpus.done", total_written=total_written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
