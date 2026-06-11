"""Indexer CLI entry point.

Usage:
    python -m indexer schema-init [--force-drop]
    python -m indexer stats
    python -m indexer search "your query" [--k 5]
    python -m indexer config
"""

from __future__ import annotations

import json
import sys

import structlog
import typer

from indexer.config import IndexerSettings, get_settings
from indexer.embedders.ollama_embedder import OllamaEmbedder
from indexer.store.connection import build_pool
from indexer.store.repository import count_rows, dense_search, hybrid_search, init_schema

log = structlog.get_logger(__name__)
app = typer.Typer(
    name="indexer",
    no_args_is_help=True,
    add_completion=False,
    help="Embed gold chunks into Oracle 23ai and search them.",
)


def _settings_from_cli() -> IndexerSettings:
    return get_settings()


@app.command("schema-init")
def cmd_schema_init(
    force_drop: bool = typer.Option(
        False,
        "--force-drop",
        help="Drop chunks_embed before re-creating. Loses all embeddings.",
    ),
) -> None:
    """Create chunks_embed table + HNSW + Oracle Text + B-tree indexes."""
    settings = _settings_from_cli()
    pool = build_pool(settings)
    try:
        init_schema(pool, force_drop=force_drop)
        typer.echo("Schema initialised.")
    finally:
        pool.close()


@app.command("stats")
def cmd_stats() -> None:
    """Print row counts per embedding_model_version."""
    settings = _settings_from_cli()
    pool = build_pool(settings)
    try:
        counts = count_rows(pool)
        total = counts.pop("_total", 0)
        typer.echo(f"Total rows: {total}")
        if counts:
            typer.echo("Per model_ver:")
            for ver, n in sorted(counts.items()):
                typer.echo(f"  {ver}: {n}")
        else:
            typer.echo("(table is empty)")
    finally:
        pool.close()


@app.command("search")
def cmd_search(
    query: str = typer.Argument(..., help="Search query text."),
    k: int = typer.Option(5, "--k", help="Number of results to return."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    use_hybrid: bool = typer.Option(False, "--hybrid", help="Use hybrid ANN+FTS via RRF."),
) -> None:
    """Embed the query and run dense ANN search (or hybrid ANN+FTS with --hybrid)."""
    settings = _settings_from_cli()

    with OllamaEmbedder(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
        dimension=settings.embedding_dim,
        timeout_seconds=settings.embed_timeout_seconds,
    ) as embedder:
        vectors = embedder.embed_batch([query])
        query_vec = vectors[0]

    pool = build_pool(settings)
    try:
        if use_hybrid:
            results = hybrid_search(
                pool,
                query_vector=query_vec,
                query_text=query,
                k=k,
                embedding_model_ver=settings.embedding_model_version,
            )
        else:
            results = dense_search(
                pool,
                query_vector=query_vec,
                k=k,
                embedding_model_ver=settings.embedding_model_version,
            )
    finally:
        pool.close()

    if json_output:
        typer.echo(json.dumps(results, default=str, indent=2))
        return

    if not results:
        typer.echo("No results. Did you run the embed job yet?")
        return

    typer.echo(f"Top {len(results)} results for: {query!r}\n")
    for rank, row in enumerate(results, start=1):
        dist = row.get("distance")
        rrf = row.get("rrf_score")
        score_str = f"rrf={rrf:.4f}" if rrf is not None else f"dist={dist:.4f}"
        head = (row.get("chunk_text_head") or "")[:220].replace("\n", " ")
        typer.echo(
            f"#{rank}  {score_str}  source={row.get('source'):<11} "
            f"doc={row.get('doc_id', '')[:10]}...  chunk_idx={row.get('chunk_index')}"
        )
        if row.get("title"):
            typer.echo(f"      title: {row['title']}")
        if head:
            typer.echo(f"      text:  {head}...")
        typer.echo("")


@app.command("config")
def cmd_config() -> None:
    """Print the resolved configuration (without secrets)."""
    s = _settings_from_cli()
    safe = s.model_dump()
    safe["oracle_password"] = "***"
    typer.echo(json.dumps(safe, indent=2, default=str))


def main() -> None:
    try:
        app()
    except Exception as exc:
        log.error("indexer.cli.failed", error=str(exc))
        typer.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
