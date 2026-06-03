import pymupdf  # PyMuPDF
from ingestion.extractors.base import ExtractionResult, Extractor


class PDFExtractor(Extractor):
    """Fast, layout-aware PDF text extractor using PyMuPDF.

    Alternatives & trade-offs:
    - unstructured: better at headers/tables but ~5x slower and heavier deps.
    - pdfplumber: best-in-class tables, weaker on text flow.
    - LlamaParse: managed (cost + network dep), great accuracy for complex PDFs.

    PyMuPDF is the right default for tech docs: clean text, good speed.
    """

    def extract(self, url: str, raw: bytes) -> ExtractionResult:
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            title = (doc.metadata or {}).get("title") or None
            pages = [page.get_text("text") for page in doc]
        text = "\n\n".join(p.strip() for p in pages if p and p.strip())
        return ExtractionResult(
            text=text,
            title=title,
            section=None,
            raw_bytes=raw,
            raw_ext="pdf",
            extra={"page_count": len(pages)},
        )
