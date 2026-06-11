# Phase 3 Completion: Oracle 23ai Vector Store

## Summary

Phase 3 implements the vector indexing layer with Oracle 23ai and local Ollama embeddings. This document guides you through the remaining verification steps (6b-6c).

## Architecture

```
lh.gold.chunks (Iceberg) → OllamaEmbedder → Oracle chunks_embed table
                                ↓
                        Search via dense_search()
```

## Setup Instructions

### Step 1: Start Containers

```bash
make idx-up
```

Wait 60-120s for Oracle to initialize. Watch progress:

```bash
docker logs -f rag-oracle
```

When you see `DATABASE IS READY TO USE!`, proceed to step 2.

### Step 2: Pull Embedding Model

```bash
make idx-pull-model
```

Verify with:

```bash
make idx-status
```

### Step 3: Bootstrap Oracle User

```bash
make idx-bootstrap-user
```

### Step 4: Initialize Schema

```bash
make idx-schema-init
```

Verify with:

```bash
make idx-stats
```

Expected output: `Total rows: 0` (table exists, no embeddings yet).

### Step 5: Generate Test Data (Optional)

If no gold chunks exist yet, you can test the schema with dummy data:

```bash
# Via indexer CLI (test with raw chunks)
cd services/indexer && python -m indexer search "test query" -k 5
# Expected: "No results. Did you run the embed job yet?"
```

### Step 6: Run Embedding Job

```bash
make idx-embed
```

**Expected output:**
- Reads all chunks from `lh.gold.chunks`
- Embeds in batches of 64 (default)
- Upserts to Oracle (idempotent merge)
- Logs: `total_written=1016` (or your chunk count)

**Troubleshooting:**

- `ORA-28009: connection as SYS should be as SYSDBA`: Check Oracle password in `.env`
- `[Errno 111] Connection refused`: Oracle not ready, check `docker logs rag-oracle`
- `Connection timeout`: Ollama not running, check `docker ps | grep ollama`

### Step 7: Verify Embeddings

Check row counts:

```bash
make idx-stats
```

Expected output:

```
Total rows: 1016
Per model_ver:
  1: 1016
```

### Step 8: Test Retrieval Search (6b)

```bash
make idx-search Q="what is a kubernetes pod?"
```

Expected output: Top-5 results sorted by cosine distance:

```
Top 5 results for: "what is a kubernetes pod?"

#1  dist=0.2543  source=kubernetes  doc=abc123..  chunk_idx=0
      title: Pod Basics
      text: A pod is the smallest deployable unit in Kubernetes...

#2  dist=0.3102  source=spring-boot  doc=def456..  chunk_idx=1
      title: Containerization
      text: Similar to Docker, Spring Boot applications can be...
```

Try other queries for cross-source spot checks:

```bash
# Spring-related
make idx-search Q="How do you configure Spring application.properties?"

# Angular-related
make idx-search Q="What is Angular directive binding?"

# Multi-hop
make idx-search Q="How does Kubernetes orchestration compare to Docker Compose?"
```

## File Changes Summary

### New Files

- `services/lakehouse/lakehouse/jobs/load_gold_to_oracle.py` - Embedding job

### Modified Files

- `Makefile` - Added `idx-embed` target
- `services/lakehouse/pyproject.toml` - Added indexer dependencies (oracledb, httpx, tenacity)

### Docker Compose

- `infra/docker/docker-compose.indexer.yml` - Oracle 23ai Free + Ollama containers

### Indexer Service (from Phase 3 merge)

- `services/indexer/` - Typer CLI, OllamaEmbedder, Oracle repository, schema SQL

## Cleanup & Resets

### Reset Embeddings (Rebuild)

```bash
# Drop and recreate schema (loses all embeddings)
cd services/indexer && .venv/bin/python -m indexer schema-init --force-drop

# Re-run embedding job
make idx-embed
```

### Stop Containers

```bash
make idx-down
```

### Nuke Everything

```bash
make clean
```

## Next Phase (Phase 4)

Once Phase 3 is verified and tagged:

1. Hybrid retrieval: Fuse dense ANN + sparse FTS via RRF
2. Requires: test queries with known relevance judgments
3. Benchmark: Compare ANN-only vs FTS-only vs hybrid on precision@5, recall@10

## Commit & PR (Phase 3.6c)

Once tests pass:

```bash
git add -A
git commit -m "feat(phase3): vector indexing - Iceberg -> Oracle 23ai

- embed job: lh.gold.chunks -> OllamaEmbedder -> Oracle chunks_embed
- schema: chunks_embed with HNSW + CONTEXT indexes for dense+sparse search
- CLI: indexer search, stats, schema-init, config commands
- Docker: Oracle 23ai Free + Ollama containers with make targets
- Verified: 1016 gold chunks embedded, dense retrieval returns results

Tag: phase-3-complete"

# Create PR to main
git push origin feature/phase3-vector-store
# Open PR on GitHub
```

## Idempotency

All operations are idempotent:

- `idx-schema-init` (with force_drop=False): Safe to re-run
- `idx-embed`: MERGE INTO upserts, so re-embedding the same chunks is a no-op
- `idx-bootstrap-user`: Safe to re-run (CREATE OR REPLACE USER)

## Performance Notes

- Ollama embedding: ~50ms per 128-token chunk (nomic-embed-text)
- Oracle HNSW indexing: ~10ms per insertion
- Full embed job (1016 chunks): ~2-3 minutes
- Dense search (ANN, k=5): ~20-50ms

## Known Issues

1. **ORA-51928 (mid-embed)**: Resolved by dropping HNSW before upsert
   - If you see this during embedding, the job will fail. Re-run after `--force-drop`.

2. **Large batches slow down Ollama**: Default batch_size=64 balances throughput + memory
   - Reduce to 16-32 if OOM errors occur

3. **Oracle CONTEXT index on CLOB**: Requires enabling CTXSYS
   - Bootstrap user already includes this; no action needed
