# RAG Lakehouse — Conversation Guide
> This document shows the **exact prompts** used to build this project phase by phase.
> Use this as a script when reproducing the project with Claude.
> Each section shows: what to type, what errors you'll hit, and how to fix them.

---

## How to use this guide

1. Open a new Claude conversation at claude.ai
2. Start with the **Session Opener** below
3. Follow each phase in order — paste the prompt, run the commands, paste output back
4. When you hit an error, check the **Errors & Fixes** section for that phase
5. Never skip phases — each one depends on the previous

---

## Session Opener

Paste this at the start of every new Claude session:

```
I am building a RAG Lakehouse project — a production-shaped Retrieval-Augmented
Generation system. Here is the context:

- Repo: github.com/[YOUR_USERNAME]/rag-lakehouse
- Stack: Oracle 23ai + Apache Iceberg + Ollama + LangChain + LangGraph + FastAPI + Angular 17
- OS: Ubuntu 24, 16 GiB RAM, Docker installed, Python 3.12, uv, Node.js 20
- Package manager: uv for Python, npm for Node

I am on Phase [N]. Here is where we left off:
[paste last 5 lines of your terminal output]

Continue from where we left off. Give me 2-3 steps at a time.
Wait for my output before continuing.
```

---

## Phase 0 — Monorepo Scaffold

### Prompt
```
Set up a production monorepo for a RAG Lakehouse project. I need:
- GitHub repo named rag-lakehouse
- Monorepo structure with services/ directory
- pre-commit hooks: ruff, ruff-format, trailing-whitespace, end-of-file-fixer
- GitHub Actions CI: ruff check on every PR
- Root pyproject.toml for tooling config
- Makefile with help target
- ADR-001 documenting the monorepo decision
- .env.example with placeholder values

Guide me step by step. Give me 2-3 steps at a time.
```

### What Claude will do
Create the repo scaffold, pyproject.toml, .pre-commit-config.yaml, GitHub Actions workflow, and Makefile.

### Errors you may hit

**Error**: `pre-commit` not found
```
Fix: pip install pre-commit
```

**Error**: `ruff` version mismatch in pyproject.toml
```
Fix: Use ruff>=0.6 in dev dependencies. Run: uv pip install ruff --upgrade
```

**Error**: GitHub Actions fails on first push
```
Fix: Make sure .github/workflows/ci.yml uses actions/checkout@v4 not v3.
The ruff version in CI must match local.
```

---

## Phase 1 — Document Ingestion

### Prompt
```
Build a document ingestion service for the RAG Lakehouse. I need:
- services/ingest/ — async BFS web crawler using httpx + BeautifulSoup
- PDF extractor using pypdf
- Stores raw HTML/text to MinIO bronze bucket as objects
- Typer CLI: crawl, pdf, list-sources commands
- Sources to crawl:
  - https://kubernetes.io/docs/concepts/ (max 50 pages)
  - https://docs.spring.io/spring-boot/reference/ (max 50 pages)
  - https://angular.dev/overview (max 50 pages)
- Docker Compose for MinIO (port 9000/9001)
- Make target: make ingest-crawl SOURCE=kubernetes

Guide me step by step.
```

### Errors you may hit

**Error**: MinIO bucket not found
```
Fix: Create bucket first:
docker exec rag-minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec rag-minio mc mb local/lakehouse
```

**Error**: Playwright not installed for JS-heavy pages
```
Fix: pip install playwright && playwright install chromium
Use as fallback only — most docs pages work with plain httpx.
```

**Error**: Too many redirects on angular.dev
```
Fix: Set follow_redirects=True in httpx client and add User-Agent header.
```

---

## Phase 2 — Iceberg Medallion Lakehouse

### Prompt
```
Build an Apache Iceberg medallion lakehouse on top of MinIO. I need:
- Docker Compose: MinIO + Iceberg REST catalog + PySpark container
- services/lakehouse/ — three PySpark jobs:
  1. bronze_to_silver.py: clean HTML → structured text, deduplicate
  2. silver_to_gold.py: chunk text (800 chars, 100 overlap) → gold chunks table
  3. embed_chunks.py: embed gold chunks via Ollama (attempt — may fail due to RAM)
- Iceberg tables: bronze.raw_docs, silver.clean_docs, gold.chunks
- Storage: MinIO s3a:// via Iceberg REST catalog
- Make targets: lake-up, lake-down, lake-etl

The gold table should have columns:
chunk_id, doc_id, source, chunk_index, text, title, source_url, char_count, chunked_at

Guide me step by step.
```

### Errors you may hit

**Error**: PySpark OOM during embed_chunks.py
```
Symptom: Job starts, reads 1016 rows, 4 partition workers start, then silent hang.
Root cause: Spark default 1GiB executor × 4 partitions = 4GiB — Linux OOM killer reaps JVM.

Fix: Add --conf spark.driver.memory=512m --conf spark.executor.memory=512m
     and repartition(2) in embed_chunks.py

Better fix: Skip PySpark for embedding. Use plain Python loader instead (Phase 3).
The Spark embed job stays as a production-pattern demonstration.
```

**Error**: s3a:// connection refused
```
Fix: Check S3_ENDPOINT env var. Inside Spark container it must be http://minio:9000
     (Docker service name), not http://localhost:9000.
```

**Error**: Iceberg table not found
```
Fix: Run bronze_to_silver.py before silver_to_gold.py.
     Tables are created on first write — order matters.
```

---

## Phase 3 — Oracle 23ai Vector Store

### Prompt
```
Build the Oracle 23ai vector store layer. I need:
- Docker Compose: Oracle 23ai Free + Ollama containers on ragnet network
- services/indexer/ Python package (uv-managed, Python 3.12)
- OllamaEmbedder class: httpx client, batch embedding, tenacity retry
- Oracle schema: chunks_embed table with VECTOR(768,FLOAT32), HNSW index, Oracle Text index
- repository.py: init_schema, upsert_chunks (MERGE INTO + executemany), dense_search
- Typer CLI: schema-init, stats, search, config commands
- Plain Python loader (scripts/load_gold.py): reads MinIO parquet → embeds → upserts
- Make targets: idx-up, idx-schema-init, idx-embed, idx-stats, idx-search

Critical Oracle setup:
- Oracle user must be on USERS tablespace (ASSM) for VECTOR type
- vector_memory_size must be set to 512M before creating HNSW index
- HNSW index blocks DML — use drop-load-rebuild pattern

Guide me step by step.
```

### Errors you will definitely hit (in order)

**Error 1**: ORA-43853 — VECTOR type not supported on tablespace
```
Symptom: CREATE TABLE with VECTOR column fails.
Root cause: VECTOR requires ASSM tablespace. System tablespace is DMT by default.

Fix:
CREATE USER rag IDENTIFIED BY RagApp_2026
  DEFAULT TABLESPACE USERS  -- must be USERS, not SYSTEM
  TEMPORARY TABLESPACE TEMP;
GRANT CONNECT, RESOURCE, UNLIMITED TABLESPACE TO rag;
```

**Error 2**: ORA-51961 — vector_memory_size is 0
```
Symptom: CREATE VECTOR INDEX fails.
Root cause: Oracle 23ai defaults vector_memory_size to 0.

Fix (run as sysdba):
ALTER SYSTEM SET vector_memory_size = 512M SCOPE=SPFILE;
-- Then restart the container:
docker restart rag-oracle
-- Wait 60 seconds for Oracle to restart.
```

**Error 3**: SPFILE changes lost after container restart
```
Symptom: vector_memory_size resets to 0 after docker restart.
Root cause: SPFILE in container is not persisted.

Fix — PFILE roundtrip:
CREATE PFILE='/tmp/init.ora' FROM SPFILE;
-- Edit /tmp/init.ora to add: vector_memory_size=536870912
CREATE SPFILE FROM PFILE='/tmp/init.ora';
-- Restart Oracle.
```

**Error 4**: ORA-51928 — HNSW blocks DML
```
Symptom: executemany() during upsert fails with ORA-51928.
Root cause: Oracle HNSW INMEMORY NEIGHBOR GRAPH does not support concurrent DML.

Fix — drop-load-rebuild pattern:
drop_vector_index(pool)    # DROP INDEX chunks_embed_hnsw_idx
upsert_chunks(pool, rows)  # MERGE INTO — works without index
rebuild_vector_index(pool) # CREATE VECTOR INDEX — rebuilds from all rows

Add this to load_gold.py and expand_corpus.py.
```

**Error 5**: boto3 / pyarrow not in venv
```
Symptom: ModuleNotFoundError when running load_gold.py
Fix: cd services/indexer && uv pip install boto3 pyarrow
     Also add to pyproject.toml dependencies.
```

**Error 6**: MinIO connection refused from load_gold.py
```
Symptom: botocore.exceptions.EndpointConnectionError
Root cause: MinIO container not running.
Fix: make lake-up && sleep 5, then retry.
```

**Error 7**: Ollama ReadTimeout on first embed batch
```
Symptom: httpx.ReadTimeout after 60 seconds on first embed call.
Root cause: Ollama loads model into RAM on first call — takes 15-30 seconds.
             Default timeout too short for batch_size=32.

Fix:
embed_timeout_seconds: int = Field(default=300)  # in config.py
embed_batch_size: int = Field(default=8)          # smaller batches
```

### Verification
```bash
# Should print: Total rows: 1016
cd services/indexer && .venv/bin/python -m indexer stats

# Should return 5 ranked chunks
.venv/bin/python -m indexer search "what is a kubernetes pod?" --k 5
```

---

## Phase 4 — Hybrid Retrieval

### Prompt
```
Add hybrid retrieval to the indexer using Oracle Text FTS + ANN fused via RRF. I need:
- _sanitize_fts_query(): strip Oracle Text special chars + English stopwords + AND-join terms
- fts_search(): Oracle Text CONTAINS query, SCORE(1) label, empty-query guard
- reciprocal_rank_fusion(): RRF with rrf_k=60, handles single-list case
- hybrid_search(): fetch 20 from each sub-search, fuse, return top-k
- --hybrid flag on the search CLI command
- idx-search-hybrid Make target
- tests/test_rrf.py: 4 contract tests (no live Oracle needed)

The FTS sanitizer is critical — without it, multi-word queries return 2 results.
```

### Errors you will hit

**Error**: FTS returning only 2 results for "kubernetes pod"
```
Symptom: oracle.fts_search k=20 returned=2
Root cause: _sanitize_fts_query() was doing simple strip() without
            removing stopwords. "what is a kubernetes pod" passed to
            CONTAINS as a phrase search — almost no chunk contains
            that exact phrase.

Fix: Strip stopwords ("what", "is", "a") and AND-join the rest:
     "what is a kubernetes pod" → "kubernetes AND pod"
     This raises fts_search returns from 2 to 20.
```

**Error**: DRG-50901 text query parser syntax error
```
Symptom: When make idx-ask is run without Q= argument.
Root cause: Empty string passed to CONTAINS.

Fix: Add guard in fts_search():
if not oracle_query.strip():
    log.info("oracle.fts_search.skipped", reason="empty_query")
    return []
```

**Error**: Oracle Text index returns 0 after bulk load
```
Symptom: CONTAINS returns 0 rows even though data exists.
Root cause: Oracle Text CONTEXT index needs SYNC after bulk DML.

Fix:
docker exec rag-oracle bash -c "echo \"
EXEC CTX_DDL.SYNC_INDEX('CHUNKS_EMBED_TEXT_IDX');
\" | sqlplus -s rag/RagApp_2026@FREEPDB1"

Better fix: Create index with SYNC (ON COMMIT) parameter:
CREATE INDEX ... PARAMETERS ('SYNC (ON COMMIT)')
```

---

## Phase 5 — LLM Generation

### Prompt
```
Add LLM answer generation to the indexer using LangChain + Ollama. I need:
- services/indexer/indexer/rag_chain.py:
  - _build_context(): number chunks, include title/source/url, truncate at rag_max_context_chars
  - build_rag_chain(): LCEL chain using OllamaLLM, temperature=0.1, streaming
  - ask(): streams tokens via chain.stream()
  - build_citations(): numbered citation list
- ask command in CLI: --hybrid/--dense flag (hybrid default), --citations flag
- config additions: ollama_llm_model, llm_timeout_seconds, rag_max_context_chars, rag_top_k
- langchain, langchain-ollama, langchain-core added to pyproject.toml
- idx-ask Make target
- tests/test_rag_chain.py: 4 contract tests for context building + citations

System prompt must restrict answers to provided context only — no hallucination.
```

### Errors you will hit

**Error**: ModuleNotFoundError: No module named 'indexer.rag_chain'
```
Root cause: rag_chain.py file wasn't created on the current branch.
Fix: git show origin/feature/phase5-llm-generation:services/indexer/indexer/rag_chain.py > services/indexer/indexer/rag_chain.py
```

**Error**: LLM hangs for 3+ minutes with no output
```
Symptom: rag.ask log line appears but no tokens stream.
Root cause: llama3.1:8b needs ~5GiB RAM. If RAM is tight, OOM kills it silently.

Fix: Switch to llama3.2:3b (only ~2GiB):
docker exec rag-ollama ollama pull llama3.2:3b
Update config: ollama_llm_model = "llama3.2:3b"

Wait 60 seconds on first call — model loads into RAM cold.
Do NOT Ctrl-C. It will respond.
```

**Error**: 'IndexerSettings' object has no attribute 'rag_top_k'
```
Root cause: LLM config fields missing from config.py on current branch
            (lost during branch conflict resolution).

Fix: Add to config.py:
ollama_llm_model: str = Field(default="llama3.2:3b")
llm_timeout_seconds: int = Field(default=120)
rag_max_context_chars: int = Field(default=6000)
rag_top_k: int = Field(default=5)
```

### Verification
```bash
make idx-ask Q="what is a kubernetes pod?"
# Expected: streams answer + 3-4 citations with real kubernetes.io URLs
# oracle.fts_search returned=20 (not 2)
# rag.ask chunks_used=3-5
```

---

## Phase 6 — LangGraph Agent

### Prompt
```
Build a LangGraph multi-agent RAG orchestrator. I need:
- services/indexer/indexer/agent.py:
  - AgentState TypedDict: question, augmented_question, intent, query_vector,
    chunks, answer_parts, citations, retry_count, final_answer
  - router_node: heuristic classifier — factual/multi_hop/ambiguous (no LLM call)
  - make_retriever_node(settings, pool): factory pattern for closure over settings
  - make_generator_node(settings): calls ask(), collects streamed tokens
  - make_reranker_node(settings, pool): quality check, retry once if poor answer
  - _should_retry(): conditional edge — "retriever" if poor + retry_count==1, else END
  - build_graph(): StateGraph with conditional edges
  - run_agent(): public API
- agent command in CLI: --trace flag
- idx-agent Make target
- tests/test_agent.py: 6 contract tests for router + retry logic

Use langgraph>=0.2. Install: uv pip install langgraph
```

### Errors you will hit

**Error**: langgraph has no __version__ attribute
```
Symptom: AttributeError: module 'langgraph' has no attribute '__version__'
Root cause: LangGraph doesn't expose __version__ directly.

Fix: Use importlib.metadata instead:
import importlib.metadata
print(importlib.metadata.version('langgraph'))
This is not an error — langgraph is installed correctly.
```

**Error**: test_router_ambiguous fails
```
Symptom: assert 'ambiguous' == 'factual' for question "what is it"
Root cause: Router checked len(words) <= 2 but "what is it" has 3 words.

Fix: Change threshold to <= 3:
elif len(words) <= 3 and any(w in ambiguous_signals for w in words):
```

**Error**: ModuleNotFoundError: No module named 'indexer.rag_chain' when running agent
```
Root cause: rag_chain.py exists on phase-5 branch but not current branch.
Fix: git show origin/feature/phase5-llm-generation:services/indexer/indexer/rag_chain.py > services/indexer/indexer/rag_chain.py
```

### Verification
```bash
make idx-agent Q="what is a kubernetes pod?"
# Expected output:
# agent.router intent=factual
# agent.retriever chunks=5
# agent.generator answer_chars=64
# agent.reranker.accept retries=0
# Answer: A Pod is the smallest deployable unit...
# Sources: [1] Workloads (kubernetes)
```

---

## Phase 7 — FastAPI Gateway

### Prompt
```
Build a FastAPI gateway for the RAG Lakehouse. I need:
- services/api/ — new Python service (separate from indexer)
- api/routes/health.py: GET /health → {status, oracle, ollama}
- api/routes/search.py: GET /search?q=...&k=5&mode=hybrid|dense → ranked chunks JSON
- api/routes/ask.py: POST /ask → SSE stream (event:token, event:citations, event:done)
- api/metrics.py: Prometheus counters + histograms + GET /metrics endpoint
- api/config.py: APISettings mirroring IndexerSettings
- api/main.py: FastAPI app with CORS, all routers registered
- The indexer must be installed into the API venv: uv pip install -e "../indexer"
  NEVER use sys.path hacks — they break when uvicorn changes directory.
- services/api/pyproject.toml with fastapi, uvicorn[standard], prometheus-client
- api-up Make target

SSE format: event: token\ndata: "text"\n\n
```

### Errors you will hit

**Error**: ModuleNotFoundError: No module named 'indexer' in search.py
```
Symptom: 500 error on /search, uvicorn log shows ModuleNotFoundError.
Root cause: sys.path.insert(0, "services/indexer") uses relative path.
            When uvicorn runs from services/api/, it resolves to
            services/api/services/indexer which doesn't exist.

Fix: Install indexer as editable dep in API venv:
cd services/api
uv pip install -e "../indexer"
Then remove all sys.path.insert lines from routes.
```

**Error**: uv pip install fails — no pip binary in venv
```
Symptom: bash: .venv/bin/pip: No such file or directory
Root cause: uv creates venvs without pip binary by default.

Fix: Always use: uv pip install (not .venv/bin/pip install)
Or: .venv/bin/python -m pip install
```

**Error**: Prometheus metrics not showing rag_ prefix
```
Symptom: /metrics returns only python_gc and process metrics.
Root cause: Metrics registered but search endpoint not instrumented.

Fix: Add timing and counter calls inside the search() function:
t0 = time.perf_counter()
# ... do search ...
RETRIEVAL_LATENCY.observe(time.perf_counter() - t0)
SEARCH_RESULT_COUNT.observe(len(rows))
REQUEST_COUNT.labels(endpoint="/search", method="GET", status="200").inc()
```

### Verification
```bash
# Terminal 1
cd services/api && .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 2
curl -s http://localhost:8000/health | python3 -m json.tool
# {"status": "ok", "oracle": "up", "ollama": "up"}

curl -s "http://localhost:8000/search?q=kubernetes+pod&k=3&mode=hybrid" | python3 -m json.tool
# Returns 3 ranked chunks with source_url and scores

curl -N -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "what is a kubernetes pod?", "k": 3}'
# Streams: event: token\ndata: "A"\n\nevent: token\ndata: " Pod"...

curl -s http://localhost:8000/metrics | grep "rag_"
# rag_retrieval_latency_seconds_bucket, rag_api_requests_total, etc.

# Swagger UI
# Open http://localhost:8000/docs in browser
```

---

## Phase 8 — Angular 17 UI

### Prompt
```
Build an Angular 17 standalone UI for the RAG Lakehouse. I need:
- services/ui/ — Angular 17 app scaffolded with ng new
  Flags: --standalone --skip-git --skip-tests --style=scss --routing=false
- src/app/services/api.service.ts:
  - health(): GET /health
  - search(): GET /search → Observable<SearchResponse>
  - fetchAsk(): POST /ask → ReadableStream for SSE token parsing
- src/app/components/query/query.component.ts:
  - Signals: loading, answer, sources, searchResults, error
  - ask(): parses SSE stream via fetch ReadableStream
  - search(): uses HttpClient Observable
- Clean SCSS styling (no external UI library needed)
- provideHttpClient() in app.config.ts
- zone.js (not zoneless) for change detection

IMPORTANT: Use zone.js. Do NOT use provideZonelessChangeDetection().
Without zone.js, click handlers won't fire.
```

### Errors you will hit

**Error**: App shows Angular default welcome page
```
Symptom: http://localhost:4200 shows "Hello, rag-ui Congratulations!" page.
Root cause: Angular 17 generates app.ts + app.html (not app.component.ts).
            We edited app.component.ts but Angular uses app.ts.

Fix:
# Update the CORRECT file
cat src/app/app.ts  # check this is the root component
# Edit app.ts to import and use QueryComponent
# Clear app.html (leave it empty — use inline template in app.ts)
echo "" > src/app/app.html
```

**Error**: Buttons not clickable / no response on click
```
Symptom: UI renders but Ask and Search buttons do nothing.
Root cause: provideZonelessChangeDetection() in app.config.ts.
            Angular's zoneless mode requires explicit markForCheck() calls.

Fix:
1. Remove provideZonelessChangeDetection() from app.config.ts
2. npm install zone.js --save
3. Add to src/main.ts: import 'zone.js';  (first line)
4. Restart ng serve
```

**Error**: npm list zone.js shows (empty)
```
Fix: npm install zone.js --save
Then add import 'zone.js'; as FIRST line in src/main.ts
```

**Error**: ApiService not injectable / HttpClient not found
```
Fix: Add provideHttpClient() to app.config.ts providers array.
import { provideHttpClient } from '@angular/common/http';
```

### Verification
Open http://localhost:4200. You should see:
```
RAG Lakehouse
Kubernetes · Spring Boot · Angular docs
[query input] [Hybrid ▾] [Ask] [Search]
```
Type "kubernetes pod" → click Search → results appear below.
Type "what is a kubernetes pod?" → click Ask → "Thinking..." → tokens stream in.

---

## Phase 9 — Observability

### Prompt
```
Add Prometheus metrics + Grafana to the RAG Lakehouse. I need:
- services/api/api/metrics.py:
  - REQUEST_COUNT counter (labels: endpoint, method, status)
  - RETRIEVAL_LATENCY histogram (buckets: 0.05 to 5.0s)
  - LLM_LATENCY histogram (buckets: 1 to 120s)
  - SEARCH_RESULT_COUNT histogram
  - GET /metrics endpoint using prometheus_client.generate_latest()
- Instrument search.py with timing + counters
- infra/docker/docker-compose.observability.yml:
  prom/prometheus:v2.53.0 + grafana/grafana:11.1.0 on ragnet
- infra/docker/prometheus.yml: scrape config pointing to host.docker.internal:8000
- obs-up, obs-down Make targets

Install: uv pip install prometheus-client --python .venv/bin/python
```

### Errors you may hit

**Error**: prometheus_client has no __version__
```
Symptom: AttributeError: module 'prometheus_client' has no attribute '__version__'
Root cause: prometheus_client doesn't expose __version__.
This is NOT an error — it installed correctly. Just verify with:
uv pip show prometheus-client
```

**Error**: /metrics returns no rag_ metrics after hitting /search
```
Root cause: metrics.py registered but search.py not instrumented.
Fix: Add t0 = time.perf_counter() before pool.build_pool()
     Add RETRIEVAL_LATENCY.observe(...) before return SearchResponse()
     Add REQUEST_COUNT.labels(...).inc() before return
```

### Verification
```bash
make obs-up
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)

# Hit the API a few times
curl -s "http://localhost:8000/search?q=kubernetes&k=3" > /dev/null

# Check metrics
curl -s http://localhost:8000/metrics | grep "rag_retrieval_latency"
# Should show histogram with real values (e.g., 0.054 seconds)
```

---

## Phase 10 — RAGAS Evaluation

### Prompt
```
Build a RAGAS-style evaluation suite. Do NOT install the ragas library —
it has a broken VertexAI import in version 0.4.x that cannot be fixed without
uninstalling langchain-community. Instead, implement the 4 core metrics from scratch.

I need scripts/eval_rag.py with:
- 20 hand-curated Q&A pairs: 8 Kubernetes, 6 Spring Boot, 6 Angular
- cosine_similarity(): pure Python, no numpy needed
- answer_relevance: cosine_sim(embed(question), embed(reference))
- context_precision: fraction of chunks with similarity >= 0.3 to question
- context_recall: max chunk similarity to reference, normalized
- faithfulness: keyword overlap between reference sentences and chunk text
- run_eval(): runs all 20, prints per-question scores + aggregate
- Saves results to eval_results.json
- eval-rag Make target
```

### Errors you will hit

**Error**: ragas 0.4.3 ImportError on install
```
Symptom:
from langchain_community.chat_models.vertexai import ChatVertexAI
ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'

Root cause: ragas 0.4.x has a broken dependency on a removed langchain module.
Earlier versions (0.2.x) also broken with modern langchain.

Fix: Do NOT use ragas at all. Implement the metrics yourself.
The implementation is ~60 lines of pure Python.
This actually shows deeper understanding in interviews.
```

**Error**: eval_rag.py runs but count=0
```
Symptom: corpus.total_chunks count=0 or loader.rows_read count=0
Root cause: Script uses Path("services/indexer") as relative path.
            Make changes directory to services/indexer/ so the path
            resolves incorrectly.

Fix: Always use absolute paths in scripts:
settings = IndexerSettings(oracle_dsn="localhost:1521/FREEPDB1", ...)
# Not: IndexerSettings()  which reads from relative .env
```

**Error**: ruff E501 line too long on reference strings
```
Symptom: pre-commit blocks commit due to reference answer strings > 100 chars.
Fix: Add per-file ignore to root pyproject.toml:
[tool.ruff.lint]
per-file-ignores = {"scripts/eval_rag.py" = ["E501"]}
```

### Expected results
```
=== AGGREGATE SCORES ===
  answer_relevance      : 0.7770
  context_precision     : 1.0000
  context_recall        : 1.0000
  faithfulness          : 0.7500
```

---

## Phase 11 — EC2 Deployment

### Prompt
```
Write a comprehensive EC2 deployment guide. I need docs/deployment/ec2.md covering:
- Target architecture: t3.xlarge (4 vCPU, 16 GiB), Docker Compose, EBS 80 GiB
- AWS CLI commands to launch instance and configure security groups
- Bootstrap script: Docker, uv, Node.js, git clone
- Stack startup order: MinIO → Iceberg → Oracle → Ollama → API
- systemd service unit for FastAPI (production-grade, auto-restart)
- End-to-end curl verification from local machine
- Observability stack startup
- Cost estimate (~$130/month t3.xlarge, stop when not in use)
- Troubleshooting table for the 4 most common issues
```

No code errors in this phase — it's documentation only.

---

## Phase 12 — Corpus Expansion

### Prompt
```
Expand the corpus with Kafka and React Native documentation. I need:
- services/corpus/kafka/: kafka_overview.md, kafka_producers.md, kafka_consumers.md
  Content: topics/partitions/brokers, producer config + Java code, consumer groups + offset mgmt
- services/corpus/react-native/: rn_overview.md, rn_navigation.md, rn_state_management.md
  Content: components/StyleSheet, React Navigation stack/tab, useState/useEffect/Context
- scripts/expand_corpus.py:
  - chunk_text(): 800 chars, 100 overlap, skip chunks < 50 chars
  - load_corpus(): reads all .md from services/corpus/ recursively
  - Uses drop-HNSW → embed → upsert → rebuild pattern
  - Idempotent via MERGE INTO
  - corpus-expand Make target
```

### Errors you will hit

**Error**: corpus.total_chunks count=0
```
Symptom: Script runs but finds no markdown files.
Root cause: Make changes directory to services/indexer/.
            Path("services/corpus") resolves to
            services/indexer/services/corpus which doesn't exist.

Fix: Use absolute path in script:
CORPUS_DIR = Path(__file__).parent.parent / "services" / "corpus"
```

### Verification
```bash
make corpus-expand
# Expected: 6 docs → 13 chunks embedded

cd services/indexer
.venv/bin/python -m indexer stats
# Total rows: 1029 (1016 + 13)

.venv/bin/python -m indexer search "kafka consumer group" --k 3
# Top results: source=kafka

.venv/bin/python -m indexer search "react native navigation" --k 3
# #1 dist=0.1880 source=react-native
```

---

## Phase 13 — Final Polish

### Prompt
```
Create the final polish for the RAG Lakehouse project. I need:
- README.md with:
  - ASCII architecture diagram (Angular → FastAPI → Hybrid Retrieval → Oracle → Iceberg)
  - Tech stack table
  - Corpus breakdown (1029 chunks, 5 sources)
  - RAGAS eval results table
  - 5-step quick start guide
  - Complete Make targets reference
  - Project structure tree
  - Key engineering decisions summary
- api-up Make target (referenced in README)
- Tag v1.0.0 after merging all phases

Then clean up tags:
- Remove misplaced phase-5-complete
- Tag each phase merge commit correctly: phase-3-complete through phase-12-complete
```

### After all PRs merged — tag all phases

```bash
git log --oneline | grep "Merge pull request"
# Note the SHA for each phase merge, then:

git tag -a phase-3-complete <SHA> -m "Phase 3: Oracle 23ai vector store"
git tag -a phase-4-complete <SHA> -m "Phase 4: Hybrid retrieval via RRF"
# ... repeat for phases 5-12 ...
git tag -a v1.0.0 HEAD -m "v1.0.0 — RAG Lakehouse complete"
git push origin --tags
```

---

## Git Workflow — Common Issues

### Pre-commit AM state (happens every time)
```
Symptom: ruff-format auto-fixes a file after you staged it.
         git status shows AM (staged then modified).
         commit is blocked.

Fix: Always do this sequence:
git add -A
pre-commit run --all-files   # auto-fixes files
git add -A                   # re-stage the auto-fixed files
git commit -m "..."
```

### Branch has no upstream
```
Symptom: fatal: The current branch has no upstream branch.
Fix: git push --set-upstream origin feature/phase-N-description
```

### Merge conflicts during rebase
```
Symptom: CONFLICT (add/add) in Makefile, __main__.py, repository.py
Root cause: Phase N was built on top of Phase N-1 which wasn't merged yet.
            When you rebase onto main (which now has Phase N-1), git sees
            both sides adding the same files.

Fix: Take the feature branch version (it has both phases' changes):
git checkout --theirs Makefile
git checkout --theirs services/indexer/indexer/__main__.py
git checkout --theirs services/indexer/indexer/store/repository.py
git checkout --theirs services/indexer/pyproject.toml
git add -A
git rebase --continue  # or git cherry-pick --continue
```

### Conflict markers left in files
```
Symptom: ruff reports SyntaxError: Expected a statement on <<<<<< lines.
Root cause: git checkout --theirs didn't fully resolve — conflict markers remain.

Fix: Get the clean version from the source branch:
git show feature/phase-N-branch:services/indexer/indexer/agent.py > services/indexer/indexer/agent.py
# Repeat for each conflicted file
grep -r "^<<<<<<\|^=======\|^>>>>>>>" services/indexer/indexer/ services/indexer/pyproject.toml Makefile
# Should return nothing (venv false positives are fine)
```

### Commit didn't land (HEAD unchanged)
```
Symptom: git log shows HEAD at the wrong commit after you thought you committed.
Root cause: pre-commit blocked the commit and you didn't notice.

Fix: Check git status — if files still staged, run:
git add -A
git commit -m "your message"
```

---

## Credential Reference

| Service | Credential | Value |
|---|---|---|
| Oracle app user | user/password | rag / RagApp_2026 |
| Oracle sysdba | sys password | RagPass_2026 |
| Oracle DSN | connection string | localhost:1521/FREEPDB1 |
| MinIO | access/secret | minioadmin / minioadmin |
| MinIO port | S3 API | 9000 |
| MinIO console | Web UI | 9001 |
| Ollama | base URL | http://localhost:11434 |
| FastAPI | port | 8000 |
| Angular | port | 4200 |
| Prometheus | port | 9090 |
| Grafana | port / credentials | 3000 / admin / admin |
| Iceberg REST | port | 8181 |

---

## What NOT to prompt

These prompts will waste time or cause errors:

❌ "Install ragas and run the evaluation"
→ ragas 0.4.x is broken. Implement metrics from scratch.

❌ "Use Spark to embed the gold chunks"
→ Spark OOMs on 16GiB RAM with 1016 rows. Use plain Python loader.

❌ "Use provideZonelessChangeDetection() in Angular"
→ Click handlers won't fire without zone.js.

❌ "Use sys.path.insert to import the indexer in the API"
→ Breaks when uvicorn changes directory. Install indexer as editable dep.

❌ "Can you give me all 13 phases at once?"
→ Response will be too long and miss your specific errors.
→ Always do one phase at a time, paste outputs, fix errors before moving on.

❌ "Rebase my feature branch onto main after merging a dependency branch"
→ Causes add/add conflicts. Use cherry-pick onto a clean branch instead:
```bash
git checkout main && git pull
git checkout -b feature/phase-N-clean
git cherry-pick <SHA-of-phase-N-commit>
```

---

## Final verification — run all at once

After v1.0.0 is tagged:

```bash
# 1. Full pipeline test
make idx-ask Q="what is a kubernetes pod?"
make idx-ask Q="how does kafka consumer group work?"
make idx-ask Q="what is an Angular signal?"
make idx-agent Q="compare kubernetes deployments versus statefulsets"

# 2. Corpus coverage check
cd services/indexer
.venv/bin/python -m indexer stats
# Expected: Total rows: 1029

# 3. Eval
make eval-rag
# Expected: CP=1.000, CR=1.000, AR~0.777, F~0.750

# 4. API health
curl -s http://localhost:8000/health
# {"status":"ok","oracle":"up","ollama":"up"}

# 5. Metrics
curl -s http://localhost:8000/metrics | grep "rag_retrieval_latency_seconds_sum"
# Should show a value > 0
```

All green = project complete. Tag is v1.0.0.
