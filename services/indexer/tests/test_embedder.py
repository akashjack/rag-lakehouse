"""Contract tests for OllamaEmbedder.

These tests do NOT hit the real Ollama. They verify that the embedder
class respects the BaseEmbedder protocol and that response shape
validation works.

Live integration tests live in tests/integration/ and are run with
'pytest -m integration' (added in Step 11).
"""

from __future__ import annotations

import pytest

from indexer.embedders.base import BaseEmbedder
from indexer.embedders.ollama_embedder import OllamaEmbedder


def test_ollama_embedder_implements_base() -> None:
    """OllamaEmbedder must be a concrete BaseEmbedder."""
    e = OllamaEmbedder(
        base_url="http://example.invalid:11434",
        model="nomic-embed-text",
        dimension=768,
    )
    try:
        assert isinstance(e, BaseEmbedder)
        assert e.model_id == "nomic-embed-text"
        assert e.dimension == 768
    finally:
        e.close()


def test_ollama_embedder_empty_input_returns_empty() -> None:
    """embed_batch([]) must return [] without hitting the API."""
    e = OllamaEmbedder(
        base_url="http://example.invalid:11434",
        model="nomic-embed-text",
        dimension=768,
    )
    try:
        assert e.embed_batch([]) == []
    finally:
        e.close()


def test_ollama_embedder_can_use_context_manager() -> None:
    """`with OllamaEmbedder(...) as e:` should work and close the client."""
    with OllamaEmbedder(
        base_url="http://example.invalid:11434",
        model="nomic-embed-text",
        dimension=768,
    ) as e:
        assert e.model_id == "nomic-embed-text"


def test_base_embedder_cannot_be_instantiated() -> None:
    """BaseEmbedder is abstract — direct instantiation must raise."""
    with pytest.raises(TypeError):
        BaseEmbedder()  # type: ignore[abstract]
