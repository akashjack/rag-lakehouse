# ADR-0002: Apache Iceberg as the Lakehouse Table Format

**Status:** Accepted
**Date:** 2026-06-XX

## Context

We need a table format on top of MinIO/S3 object storage that supports:
- Schema evolution without rewriting historical data
- Time travel (snapshot isolation, AS OF queries)
- ACID writes for the medallion ETL (bronze→silver→gold)
- Engine neutrality (Spark today, Trino/DuckDB/Flink possible later)
- Hidden partitioning so query writers don't think about partition columns

## Options Evaluated

### Apache Iceberg
- Engine-neutral by design (Spark, Trino, Flink, DuckDB, Snowflake, Athena)
- Hidden partitioning + partition evolution (change partition spec
  without rewriting)
- Branching and tagging (git-like data versioning when paired with Nessie)
- Strong schema evolution (add, drop, rename, reorder, promote types)
- Manifest-tree metadata scales to petabyte tables

### Delta Lake
- Best-in-class on Databricks; ecosystem outside Databricks is improving
  but lags Iceberg
- Strong ACID semantics, change data feed
- Partition columns are visible to query writers (no hidden partitioning)
- Liquid clustering is great but Databricks-only

### Apache Hudi
- Strongest record-level upsert and CDC story
- Best for streaming ingestion with frequent updates
- Smaller ecosystem of query engines
- More operational complexity (table services, compaction, cleaning)

## Decision

**Iceberg.** Three reasons:

1. **Engine neutrality.** We use Spark in Phase 2, but a Phase 9 evaluation
   step might want DuckDB or Trino against the same tables. Iceberg makes
   that a config change, not a migration.

2. **Hidden partitioning + partition evolution.** Our partition key
   (`source`, `ingested_date`) might change as the corpus grows. Iceberg
   lets us evolve the spec without rewriting historical data — Delta
   requires a full rewrite.

3. **Branching/tagging.** When we re-chunk in Phase 4, we'll tag the
   pre-rechunk state for rollback. This is native in Iceberg.

## Trade-offs Accepted

- Iceberg metadata operations are heavier than Delta on tiny tables.
  Irrelevant at our scale (hundreds of MB).
- Iceberg's Python writers (PyIceberg) are less mature than Spark; we
  stick to Spark for writes and use PyIceberg only for reads in later
  phases if useful.

## Consequences

- Catalog choice: REST catalog (containerized, SQLite-backed) for dev.
  Production swap candidates: Nessie (git-like branching), AWS Glue,
  JDBC catalog backed by Postgres.
- Spark version pinned to 3.5.x with `iceberg-spark-runtime-3.5_2.12:1.6.1`.
- MinIO accessed via the S3A connector; same code works against real S3
  by changing endpoint + credentials.
