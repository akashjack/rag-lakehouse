from __future__ import annotations

from pathlib import Path

import structlog
from pydantic import AnyUrl

from ingestion.extractors.pdf_extractor import PDFExtractor
from ingestion.schema import DocumentMetadata, NormalizedDocument
from ingestion.storage import doc_id_exists, put_normalized, put_raw

log = structlog.get_logger(__name__)


def ingest_pdf(path: Path, source: str) -> str | None:
    raw = path.read_bytes()
    url = f"file://{path.resolve()}"
    result = PDFExtractor().extract(url, raw)
    if not result.text or len(result.text) < 200:
        log.warning("pdf.empty", path=str(path))
        return None

    doc_id = DocumentMetadata.make_doc_id(url, result.text)
    if doc_id_exists(source, doc_id):
        log.info("pdf.skip_exists", doc_id=doc_id)
        return doc_id

    raw_object_key = put_raw(source, doc_id, raw, "pdf")
    meta = DocumentMetadata(
        doc_id=doc_id,
        source=source,
        source_type="pdf",
        source_url=AnyUrl(url),
        title=result.title or path.stem,
        section=None,
        content_hash=DocumentMetadata.hash_text(result.text),
        raw_object_key=raw_object_key,
        text_object_key="",
        byte_size=len(raw),
        char_count=len(result.text),
        extra=result.extra,
    )
    doc = NormalizedDocument(metadata=meta, text=result.text)
    text_key = put_normalized(doc)
    doc.metadata.text_object_key = text_key
    put_normalized(doc)
    log.info("pdf.wrote", doc_id=doc_id, chars=len(result.text))
    return doc_id
