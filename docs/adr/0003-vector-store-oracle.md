# ADR-0003: Oracle 23ai as the Vector + Full-Text Store

**Status:** Accepted
**Date:** 2026-06-XX

## Context

The retrieval layer needs to support:
- Dense vector ANN search over 1000-100k chunk embeddings (768-dim)
- Full-text (BM25-style) search over the same chunks
- Metadata filtering (source, doc_id_prefix, etc.) alongside both
- Hybrid scoring (Reciprocal Rank Fusion of dense + sparse) without
  cross-system joins
- Single transactional write path during the embed job

## Options Evaluated

### Oracle 23ai (Free)
- Native `VECTOR(N, FLOAT32)` datatype with HNSW + IVF indexes
- Oracle Text (`CONTEXT` index) for full-text on the same row
- JSON columns for arbitrary metadata, indexable
- Transactional MERGE for idempotent upserts
- One process to operate; one schema to evolve; one query language

### Postgres + pgvector
- Most common choice in 2024-2026; mature, well-documented
- `vector` extension provides HNSW + IVFFlat
- Full-text via `tsvector` + GIN — workable but weaker than Oracle Text
  on long documents (no thesaurus, weaker scoring)
- Two extensions (vector + tsvector) coexisting; index management is
  more manual

### Qdrant / Weaviate / Milvus (purpose-built vector DBs)
- Excellent ANN performance at billion-vector scale
- Built-in BM25 / sparse support in newer versions
- Separate system from primary store → metadata sync becomes a real
  engineering problem
- Overkill for our 1k-100k chunks

### Elasticsearch / OpenSearch
- Best full-text in the industry
- kNN support is workable but vector-index latency lags purpose-built
  stores
- Heavy operationally for a single-node project

## Decision

**Oracle 23ai Free.** Three reasons:

1. **Single engine = no sync problem.** Vector embedding and full-text
   tokenization land in the same row inside the same MERGE statement.
   Hybrid retrieval (Phase 4) queries both indexes via two SQL
   statements and fuses results in application code via RRF. There
   is no risk of vector and FTS drifting out of sync.

2. **Resume differentiation.** Most RAG demos use pgvector or Qdrant.
   Oracle 23ai is a real production database that happens to have
   added vector support; the engineering exercise of using it
   demonstrates breadth.

3. **Free tier is sufficient.** The 23ai Free container has the same
   VECTOR datatype as enterprise editions. Limits (12 GB user data,
   2 CPU) are orders of magnitude beyond our needs.

## Trade-offs Accepted

- **Heavier image** (~3 GB) than pgvector or Qdrant.
- **Slower startup** (~60-90s vs ~5s for Postgres) on cold container.
- **Smaller community** for vector-specific tuning. The HNSW knobs
  (M, efConstruction, efSearch) are documented but examples are
  fewer than for pgvector or Qdrant.
- **Oracle licensing complexity** in true production. Free tier sidesteps
  this for development; if this system ever moved to enterprise scale,
  the licensing conversation would happen.

## Consequences

- Embedding store schema: one `chunks_embed` table with VECTOR(768),
  CLOB for chunk_text, CONTEXT index on chunk_text, HNSW index on
  embedding, B-tree indexes on metadata columns.
- Connectivity: `python-oracledb` thin mode (no client install).
- JDBC for PySpark writes: Oracle JDBC driver added to the Spark
  jars-extra dir.
- The `BaseVectorStore` interface (defined in services/indexer) makes
  the Oracle implementation swappable. pgvector / Qdrant adapters
  could be added in a later phase for benchmarking, but are not in
  Phase 3 scope.
