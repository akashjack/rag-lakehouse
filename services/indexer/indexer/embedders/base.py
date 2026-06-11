"""BaseEmbedder protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Abstract embedder. Concrete implementations: OllamaEmbedder."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier embedded into Oracle rows for cache invalidation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension. Must match the Oracle VECTOR(N, FLOAT32) column."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Order of return matches order of input."""
