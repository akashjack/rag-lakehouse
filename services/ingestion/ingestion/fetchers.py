from __future__ import annotations

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.config import settings

log = structlog.get_logger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def fetch_http(url: str, *, client: httpx.AsyncClient) -> bytes:
    resp = await client.get(url, follow_redirects=True, timeout=settings.request_timeout_s)
    resp.raise_for_status()
    return resp.content


async def fetch_playwright(url: str, *, attempts: int = 2) -> bytes:
    """Headless render with retry on transient errors.

    Playwright is lazy-imported because it's a heavyweight dep (Chromium driver,
    asyncio runtime hooks) that only ~10% of pages need. Importing at module
    top-level slows every CLI invocation including read-only commands like
    `list-sources`.
    """
    from playwright.async_api import async_playwright

    timeout_ms = settings.request_timeout_s * 1000
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(user_agent=settings.user_agent)
                    await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    html: str = await page.content()
                    encoded: bytes = html.encode("utf-8")
                    return encoded
                finally:
                    await browser.close()
        except Exception as e:
            last_err = e
            log.warning("playwright.retry", url=url, attempt=attempt, err=str(e))
    assert last_err is not None
    raise last_err


async def fetch_smart(url: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """Try plain HTTP first; fall back to Playwright if response looks JS-rendered."""
    raw = await fetch_http(url, client=client)
    if b"<noscript>" in raw or len(raw) < 2048:
        log.info("fetch.fallback_playwright", url=url, http_bytes=len(raw))
        return await fetch_playwright(url), "playwright"
    return raw, "http"
