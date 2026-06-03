from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from urllib.parse import urldefrag, urljoin

import httpx
import structlog
from selectolax.parser import HTMLParser

from ingestion.config import settings
from ingestion.extractors.web_extractor import WebExtractor
from ingestion.fetchers import fetch_smart
from ingestion.schema import DocumentMetadata, NormalizedDocument
from ingestion.sources import WebSource
from ingestion.storage import doc_id_exists, put_normalized, put_raw

log = structlog.get_logger(__name__)


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _extract_links(base_url: str, html: bytes, src: WebSource) -> list[str]:
    try:
        tree = HTMLParser(html.decode("utf-8", errors="replace"))
    except Exception:
        return []
    found: set[str] = set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if not href or href.startswith(("mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        absolute, _ = urldefrag(absolute)
        if any(absolute.startswith(p) for p in src.allow_prefix) and not any(
            d in absolute for d in src.deny_substr
        ):
            found.add(absolute)
    return sorted(found)


async def crawl_source(src: WebSource) -> int:
    seen: set[str] = set()
    queue: deque[str] = deque(src.seed_urls)
    extractor = WebExtractor()
    headers = {"User-Agent": settings.user_agent}
    sem = asyncio.Semaphore(settings.crawl_concurrency)
    written = 0

    async with httpx.AsyncClient(headers=headers, http2=True) as client:

        async def process(url: str) -> list[str]:
            nonlocal written
            async with sem:
                try:
                    raw, how = await fetch_smart(url, client)
                except Exception as e:
                    log.warning("crawl.fetch_failed", url=url, err=str(e))
                    return []

                result = extractor.extract(url, raw)
                if not result.text or len(result.text) < 200:
                    log.info("crawl.skip_empty", url=url, chars=len(result.text))
                    return _extract_links(url, raw, src)

                # doc_id now hashes (canonical url + normalized text), so HTML noise
                # (timestamps, CSRF tokens, build hashes) doesn't break idempotency.
                doc_id = DocumentMetadata.make_doc_id(url, result.text)

                if doc_id_exists(src.name, doc_id):
                    log.info("crawl.skip_exists", url=url, doc_id=doc_id)
                    return _extract_links(url, raw, src)

                raw_object_key = put_raw(src.name, doc_id, raw, result.raw_ext)
                meta = DocumentMetadata(
                    doc_id=doc_id,
                    source=src.name,
                    source_type="web",
                    source_url=url,
                    title=result.title,
                    section=result.section,
                    content_hash=DocumentMetadata.hash_text(result.text),
                    raw_object_key=raw_object_key,
                    text_object_key="",
                    byte_size=len(raw),
                    char_count=len(result.text),
                    extra={"fetch_method": how, **result.extra},
                )
                doc = NormalizedDocument(metadata=meta, text=result.text)
                text_key = put_normalized(doc)
                doc.metadata.text_object_key = text_key
                put_normalized(doc)
                written += 1
                log.info("crawl.wrote", url=url, doc_id=doc_id, chars=len(result.text))
                return _extract_links(url, raw, src)

        while queue and len(seen) < settings.max_pages_per_source:
            batch = []
            while queue and len(batch) < settings.crawl_concurrency:
                u = queue.popleft()
                if u in seen:
                    continue
                seen.add(u)
                batch.append(u)
            if not batch:
                break
            results = await asyncio.gather(*(process(u) for u in batch))
            for links in results:
                for link in links:
                    if link not in seen and len(seen) < settings.max_pages_per_source:
                        queue.append(link)

    log.info("crawl.done", source=src.name, pages_visited=len(seen), pages_written=written)
    return written
