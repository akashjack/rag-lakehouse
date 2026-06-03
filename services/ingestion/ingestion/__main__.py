from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import structlog
import typer

from ingestion.config import settings
from ingestion.crawler import crawl_source
from ingestion.pdf_ingest import ingest_pdf
from ingestion.sources import SOURCES

logging.basicConfig(level=settings.log_level)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

app = typer.Typer(help="RAG-lakehouse ingestion CLI")


@app.command()
def crawl(source: str = typer.Option(..., help=f"One of: {', '.join(SOURCES)}")) -> None:
    if source not in SOURCES:
        raise typer.BadParameter(f"Unknown source. Choose from: {list(SOURCES)}")
    written = asyncio.run(crawl_source(SOURCES[source]))
    typer.echo(f"Wrote {written} documents to bronze.")


@app.command()
def pdf(path: Path, source: str = "local") -> None:
    doc_id = ingest_pdf(path, source)
    typer.echo(f"doc_id={doc_id}" if doc_id else "Skipped (empty or duplicate).")


@app.command()
def list_sources() -> None:
    for name, s in SOURCES.items():
        typer.echo(f"{name}: {len(s.seed_urls)} seeds, allow={s.allow_prefix}")


if __name__ == "__main__":
    app()
