# Architecture

## High-level flow

```mermaid
flowchart LR
    subgraph Ingest [Ingestion]
        A[PDF / Web Sources] --> B[Ingestion Service<br/>PyMuPDF + Playwright]
    end

    subgraph Storage [Object Storage]
        B --> C[(MinIO<br/>bronze)]
    end

    subgraph Lakehouse [Iceberg Lakehouse]
        C --> D[PySpark ETL<br/>clean + dedupe]
        D --> E[(Iceberg<br/>silver)]
        E --> F[Chunker<br/>recursive + semantic]
        F --> G[(Iceberg<br/>gold)]
    end

    subgraph Vector [Vector + FTS]
        G --> H[Embedder<br/>Ollama nomic-embed]
        H --> I[(Oracle 23ai<br/>VECTOR + TEXT)]
    end

    subgraph Query [Query path]
        U[User] --> W[Angular UI]
        W -- SSE --> X[FastAPI Gateway]
        X --> Y[LangGraph Agent<br/>classify→retrieve→validate→synth]
        Y -.cache.-> R[(Redis)]
        Y --> I
        Y --> L[LLM<br/>llama3.1 / GPT-4o]
        L --> X
    end

    subgraph Obs [Observability]
        X --> P[(Prometheus)]
        P --> GF[Grafana]
    end
```

## Medallion zones

| Zone | Format | Content | Purpose |
|---|---|---|---|
| Bronze | Raw JSON + blobs in MinIO | Untouched scrape output | Replay / audit |
| Silver | Iceberg | Cleaned, deduped, normalized text + metadata | Queryable canonical source |
| Gold | Iceberg | Chunked, enriched with embeddings metadata | Source of truth for indexer |

## Retrieval flow

1. **Classifier** decides query type (factoid / multi-hop / out-of-scope).
2. **Retriever** runs dense ANN + sparse FTS in parallel against Oracle.
3. **RRF** fuses ranked lists (`k=60`).
4. **Validator** checks if top-k context can answer the query (LLM-as-judge, 0–1 score).
5. **Synthesizer** generates answer with `[doc_id:chunk_id]` citations. Refuses if validator < 0.5.
