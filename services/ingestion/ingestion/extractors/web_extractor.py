import trafilatura

from ingestion.extractors.base import ExtractionResult, Extractor


class WebExtractor(Extractor):
    """HTML → clean main-content text using trafilatura.

    Alternatives:
    - readability-lxml: simpler, less accurate on modern SPAs.
    - BeautifulSoup hand-rolled: full control, fragile per-site.
    - Playwright + JS render: needed only when content is JS-loaded.
      We use Playwright only at *fetch* time when required (next file).
    """

    def extract(self, url: str, raw: bytes) -> ExtractionResult:
        html = raw.decode("utf-8", errors="replace")
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=False,
            output_format="txt",
        ) or ""
        meta = trafilatura.extract_metadata(html)
        title = getattr(meta, "title", None) if meta else None
        return ExtractionResult(
            text=extracted.strip(),
            title=title,
            section=None,
            raw_bytes=raw,
            raw_ext="html",
            extra={},
        )
