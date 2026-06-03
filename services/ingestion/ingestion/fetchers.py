from __future__ import annotations

import asyncio

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


async def fetch_playwright(url: str) -> bytes:
    """JS-rendered fetch; only use when fetch_http returns near-empty content."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=settings.user_agent)
            await page.goto(url, wait_until="networkidle", timeout=settings.request_timeout_s * 1000)
            html = await page.content()
            return html.encode("utf-8")
        finally:
            await browser.close()


async def fetch_smart(url: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """Try plain HTTP first; fall back to Playwright if content seems JS-rendered.

    Returns (bytes, how) where how is 'http' or 'playwright'.
    """
    raw = await fetch_http(url, client=client)
    # crude but effective: tech docs sites usually render content server-side
    if b"<noscript>" in raw or len(raw) < 2048:
        log.info("fetch.fallback_playwright", url=url, http_bytes=len(raw))
        return await fetch_playwright(url), "playwright"
    return raw, "http"
