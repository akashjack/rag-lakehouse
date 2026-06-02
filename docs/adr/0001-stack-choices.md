# ADR-0001: Stack Choices

**Status:** Accepted
**Date:** 2024-… (today)

## Context

Build a production-grade RAG system that demonstrates lakehouse engineering, hybrid retrieval, and agentic orchestration on a local single-node setup with a documented cloud deploy path.

## Decisions

### Lakehouse: Apache Iceberg (PySpark)
- **Why:** Engine-neutral (Spark, Trino, Flink, DuckDB), branching/tagging, hidden partitioning, schema evolution without rewrites.
- **Alternatives considered:**
  - *Delta Lake* — strongest in Databricks; weaker outside it.
  - *Apache Hudi* — superior upsert/CDC; weaker ecosystem for analytics.
- **Trade-off:** Iceberg metadata operations are heavier than Delta on small tables; irrelevant at our scale.

### Vector + FTS: Oracle 23ai
- **Why:** Single engine for `VECTOR`, full-text (`CONTAINS`), JSON, and transactional metadata. Eliminates a sync problem between vector DB and metadata store.
- **Alternatives:** pgvector (most common, weaker FTS), Qdrant/Weaviate (purpose-built, separate system), Milvus (scale king but overkill here).
- **Trade-off:** Heavier container (~3GB image), Oracle licensing complexity in true production.

### Embeddings + LLM: Ollama (local), OpenAI (swap)
- **Why local:** Zero API cost during development. Reproducible, offline.
- **Why swappable:** Resume + eval claim requires GPT-4o baseline. `BaseLLM` interface allows one-line provider switch.
- **Alternatives:** vLLM (faster, GPU required), TGI (HuggingFace), llama.cpp directly.

### Orchestration: LangGraph
- **Why:** Explicit state machine with checkpoints and retries — needed for the validator-loop pattern. Plain LangChain agents are too implicit for multi-hop debugging.
- **Alternatives:** CrewAI (role-centric, less control), AutoGen (chat-centric), pure custom (more work, but no abstraction tax).

### API: FastAPI
- **Why:** Async-native, Pydantic v2, OpenAPI for free, SSE for streaming.
- **Alternatives:** Starlette (lower level), Litestar (newer, smaller ecosystem).

### Frontend: Angular 17 standalone + signals
- **Why:** Matches author's stack; demonstrates SSE consumption and citation rendering.
- **Alternatives:** Next.js (more common in AI demos), SvelteKit (smaller bundles).

### Deployment: docker-compose locally, EC2 documented
- **Why:** Single-node single-laptop reality check. Real prod would be ECS/EKS — out of scope but documented.

## Consequences

- Heavy local resource footprint: Oracle 23ai (~4GB), Spark, Ollama (~5GB for llama3.1:8b), MinIO, Redis, Prometheus/Grafana, NGINX, Angular dev server. Need 16GB RAM minimum.
- LLM swap requires running RAGAS eval against both providers once and pinning the result.
