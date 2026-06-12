# RAG Lakehouse

A production-shaped Retrieval-Augmented Generation system built on Oracle 23ai, Apache Iceberg, and local LLMs. Ingests technical documentation, stores it in a medallion lakehouse, embeds chunks into Oracle vector store, and serves hybrid search + streaming LLM answers via a FastAPI gateway and Angular UI.

---

## Architecture
                    ┌─────────────────────────────────────────┐
                    │           Angular 17 UI (port 4200)      │
                    │   Query input · SSE streaming · Citations │
                    └────────────────┬────────────────────────┘
                                     │ HTTP
                    ┌────────────────▼────────────────────────┐
                    │        FastAPI Gateway (port 8000)        │
                    │  /health  /search  /ask  /metrics         │
                    └──────┬──────────────┬────────────────────┘
                           │              │
           ┌───────────────▼──┐    ┌──────▼──────────────┐
           │  Hybrid Retrieval │    │   LangGraph Agent    │
           │  Dense ANN + FTS  │    │  Router→Retriever→  │
           │  fused via RRF    │    │  Generator→Reranker  │
           └───────┬───────────┘    └──────┬──────────────┘
                   │                       │
    ┌──────────────▼───────────────────────▼──────────────┐
    │              Oracle 23ai Free                         │
    │  chunks_embed: VECTOR(768) + HNSW + Oracle Text FTS  │
    │  1029 chunks · nomic-embed-text-v1.5                  │
    └──────────────────────────────────────────────────────┘
                   │
    ┌──────────────▼───────────────────────────────────────┐
    │           Apache Iceberg Medallion Lakehouse           │
    │  Bronze (raw HTML) → Silver (clean text) → Gold       │
    │  (chunks)  ·  MinIO object store  ·  Iceberg REST     │
    └──────────────────────────────────────────────────────┘

## Tech Stack

| Layer | Technology |
|---|---|
| Vector store | Oracle 23ai Free — HNSW index + Oracle Text FTS |
| Embeddings | Ollama nomic-embed-text-v1.5 (768-dim, local) |
| LLM | Ollama llama3.2:3b (local, no API key needed) |
| Retrieval | Hybrid: ANN + FTS fused via Reciprocal Rank Fusion |
| Agent | LangGraph — router → retriever → generator → reranker |
| Lakehouse | Apache Iceberg + MinIO + Iceberg REST catalog |
| ETL | PySpark (bronze→silver→gold medallion) |
| API | FastAPI + SSE streaming |
| UI | Angular 17 standalone components + signals |
| Observability | Prometheus + Grafana |
| Evaluation | RAGAS-style embedding metrics (4 metrics, 20 Q&A pairs) |

## Corpus

| Source | Docs | Chunks |
|---|---|---|
| Kubernetes | kubernetes.io/docs | 322 |
| Spring Boot | spring.io/docs | ~350 |
| Angular | angular.dev | ~344 |
| Apache Kafka | Hand-curated | 7 |
| React Native | Hand-curated | 6 |
| **Total** | | **1029** |

## Evaluation Results

| Metric | Score | Description |
|---|---|---|
| context_precision | **1.000** | Every retrieved chunk is relevant |
| context_recall | **1.000** | Reference always covered by chunks |
| answer_relevance | **0.777** | Strong semantic alignment |
| faithfulness | **0.750** | 75% of answers grounded in context |

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+, uv, Node.js 20+
- 8 GiB RAM minimum (16 GiB recommended)

### 1. Start the infrastructure

```bash
# Create Docker network
docker network create ragnet

# Start MinIO + Iceberg REST
docker compose -f infra/docker/docker-compose.minio.yml up -d
docker compose -f infra/docker/docker-compose.lakehouse.yml up -d

# Start Oracle 23ai + Ollama
docker compose -f infra/docker/docker-compose.indexer.yml up -d

# Wait for Oracle to initialize (~3 minutes on first boot)
sleep 180
```

### 2. Bootstrap the vector store

```bash
# Install indexer
cd services/indexer && uv venv && uv pip install -e "." && cd ../..

# Pull embedding + LLM models
docker exec rag-ollama ollama pull nomic-embed-text
docker exec rag-ollama ollama pull llama3.2:3b

# Initialize Oracle schema
make idx-schema-init

# Embed gold chunks into Oracle
make idx-embed
```

### 3. Start the API

```bash
cd services/api && uv venv && uv pip install -e "." -e "../indexer" && cd ../..
make api-up   # or: cd services/api && uvicorn api.main:app --port 8000
```

### 4. Start the UI

```bash
cd services/ui && npm install && ng serve --port 4200
```

Open http://localhost:4200

### 5. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","oracle":"up","ollama":"up"}

curl "http://localhost:8000/search?q=kubernetes+pod&k=3"
# Returns ranked chunks with citations

make idx-ask Q="what is a kubernetes pod?"
# Streams LLM answer with source citations
```

## Make Targets

| Target | Description |
|---|---|
| `make idx-schema-init` | Initialize Oracle schema + HNSW index |
| `make idx-embed` | Embed gold chunks into Oracle |
| `make idx-search Q="..."` | Dense ANN search |
| `make idx-search-hybrid Q="..."` | Hybrid ANN + FTS search via RRF |
| `make idx-ask Q="..."` | Full RAG pipeline (retrieve + generate) |
| `make idx-agent Q="..."` | LangGraph multi-agent pipeline |
| `make corpus-expand` | Embed Kafka + React Native corpus |
| `make eval-rag` | Run RAGAS-style evaluation (20 Q&A pairs) |
| `make obs-up` | Start Prometheus + Grafana |
| `make obs-down` | Stop observability stack |

## Project Structure
rag-lakehouse/

├── docs/

│   ├── adr/                    Architecture Decision Records

│   └── deployment/             EC2 deployment guide

├── infra/docker/               Docker Compose files

├── scripts/                    Eval + corpus expansion scripts

├── services/

│   ├── api/                    FastAPI gateway

│   │   └── api/routes/         /health /search /ask /metrics

│   ├── corpus/                 Kafka + React Native markdown docs

│   ├── indexer/                Oracle vector store + RAG chain

│   │   └── indexer/

│   │       ├── agent.py        LangGraph multi-agent

│   │       ├── rag_chain.py    LangChain LCEL RAG chain

│   │       └── store/          Oracle repository + connection pool

│   ├── lakehouse/              PySpark medallion ETL jobs

│   └── ui/                     Angular 17 standalone app

└── Makefile

## Key Engineering Decisions

See `docs/adr/` for full ADRs. Summary:

- **Oracle 23ai for vector store**: Combines HNSW ANN search with Oracle Text FTS in a single database. Eliminates the need for a separate vector DB (Pinecone, Weaviate) while leveraging Oracle Text's mature full-text search.
- **Hybrid retrieval via RRF**: Reciprocal Rank Fusion (Cormack et al. 2009) combines dense and sparse retrieval without learned weights. `rrf_k=60` is the standard robust default.
- **Local LLMs via Ollama**: No API keys, no egress costs, full data privacy. llama3.2:3b fits in 4 GiB RAM.
- **Python loader over PySpark for embedding**: At 1029-chunk scale, the JVM overhead of Spark outweighs the benefit. The Spark job remains as a production-pattern demonstration for larger scale.
- **LangGraph for agent orchestration**: Explicit state graph with conditional retry edges. Router uses heuristic classification (no LLM call) for sub-millisecond routing decisions.

## License

MIT
