-- =====================================================================
-- chunks_embed: dense vector + full-text store for the gold corpus
--
-- One row per (chunk_id, embedding_model_version) — re-embedding with
-- a new model version produces new rows alongside the old ones, so we
-- can A/B retrieval quality across embedders without losing the prior
-- index. (See ADR-003.)
--
-- Indexes:
--   - chunks_embed_hnsw_idx: HNSW ANN index on the VECTOR column
--   - chunks_embed_text_idx: Oracle Text CONTEXT index for Phase 4
--                            BM25-style FTS retrieval
--   - chunks_embed_doc_idx, chunks_embed_source_idx: B-tree on filter cols
-- =====================================================================

CREATE TABLE chunks_embed (
    chunk_id              VARCHAR2(64)         NOT NULL,
    doc_id                VARCHAR2(64)         NOT NULL,
    source                VARCHAR2(64)         NOT NULL,
    chunk_index           NUMBER(10)           NOT NULL,
    chunk_text            CLOB                 NOT NULL,
    title                 VARCHAR2(512),
    source_url            VARCHAR2(2048),
    char_count            NUMBER(10),
    embedding             VECTOR(768, FLOAT32) NOT NULL,
    embedding_model       VARCHAR2(128)        NOT NULL,
    embedding_model_ver   VARCHAR2(64)         NOT NULL,
    created_at            TIMESTAMP            DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP            DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chunks_embed_pk PRIMARY KEY (chunk_id, embedding_model_ver)
);

-- HNSW dense index — cosine distance, 95% target accuracy
CREATE VECTOR INDEX chunks_embed_hnsw_idx
    ON chunks_embed (embedding)
    ORGANIZATION INMEMORY NEIGHBOR GRAPH
    DISTANCE COSINE
    WITH TARGET ACCURACY 95
    PARAMETERS (TYPE HNSW, NEIGHBORS 16, EFCONSTRUCTION 200);

-- Oracle Text CONTEXT index for Phase 4 hybrid retrieval
CREATE INDEX chunks_embed_text_idx
    ON chunks_embed (chunk_text)
    INDEXTYPE IS CTXSYS.CONTEXT;

-- B-tree filter indexes
CREATE INDEX chunks_embed_doc_idx    ON chunks_embed (doc_id);
CREATE INDEX chunks_embed_source_idx ON chunks_embed (source);
