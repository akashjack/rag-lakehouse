from typing import Any

import pymupdf
from ingestion.extractors.base import ExtractionResult, Extractor


class PDFExtractor(Extractor):
    """Fast, layout-aware PDF text extractor using PyMuPDF.

    PyMuPDF ships without type stubs (it's a C extension). We type the opened
    document as `Any` to opt the whole pymupdf surface out of mypy. The
    `no-untyped-call` ignore is scoped to the single `open()` line. We don't
    use the context-manager form because pymupdf's __enter__/__exit__ also
    raises no-untyped-call once strict mode is on.

    Alternatives considered:
      - unstructured: richer layout heuristics, ~5x slower, heavier deps
      - pdfplumber: best-in-class table extraction, weaker on text flow
    PyMuPDF wins for tech docs: clean text, good speed.
    """

    def extract(self, url: str, raw: bytes) -> ExtractionResult:
        doc: Any = pymupdf.open(stream=raw, filetype="pdf")  # type: ignore[no-untyped-call]
        try:
            title = (doc.metadata or {}).get("title") or None
            pages: list[str] = [page.get_text("text") for page in doc]
        finally:
            doc.close()
        text = "\n\n".join(p.strip() for p in pages if p and p.strip())
        return ExtractionResult(
            text=text,
            title=title,
            section=None,
            raw_bytes=raw,
            raw_ext="pdf",
            extra={"page_count": len(pages)},
        )
