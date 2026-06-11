"""Ollama-backed embedder using the /api/embed endpoint."""

from __future__ import annotations

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from indexer.embedders.base import BaseEmbedder

log = structlog.get_logger(__name__)


class OllamaEmbedder(BaseEmbedder):
    def __init__(
        self,
        base_url: str,
        model: str,
        dimension: int,
        timeout_seconds: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout_seconds,
            http2=True,
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        resp = self._client.post(
            "/api/embed",
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()

        data = resp.json()
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            got = len(embeddings) if isinstance(embeddings, list) else "non-list"
            raise ValueError(
                f"Ollama returned malformed embeddings: expected {len(texts)}, got {got}"
            )

        for idx, emb in enumerate(embeddings):
            if not isinstance(emb, list) or len(emb) != self._dimension:
                actual = len(emb) if isinstance(emb, list) else "?"
                raise ValueError(f"Embedding {idx} has dim {actual}, expected {self._dimension}")

        log.debug("ollama.embed_batch", count=len(texts), model=self._model)
        return embeddings  # type: ignore[no-any-return]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaEmbedder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
