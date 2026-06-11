"""BaseEmbedder protocol.

Any embedder implementation must support batch embedding and report
its model identity + output dimension. The model identity lets us
re-key on (chunk_id, embedding_model_version) so swapping embedders
re-embeds the corpus without colliding with the previous index.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Abstract embedder. Concrete implementations: OllamaEmbedder, OpenAIEmbedder (later)."""

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
