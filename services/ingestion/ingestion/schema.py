from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, Field

SourceType = Literal["web", "pdf"]


class DocumentMetadata(BaseModel):
    doc_id: str = Field(..., description="SHA-256 of canonical source URL + normalized text")
    source: str = Field(..., description="Logical source: kubernetes|spring|angular|...")
    source_type: SourceType
    source_url: AnyUrl
    title: str | None = None
    section: str | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = Field(..., description="SHA-256 of normalized text")
    raw_object_key: str = Field(..., description="MinIO key of raw blob")
    text_object_key: str = Field(..., description="MinIO key of normalized text JSON")
    byte_size: int
    char_count: int
    extra: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def make_doc_id(source_url: str, normalized_text: str) -> str:
        """Content-addressable ID. Stable across re-crawls if the extracted text is unchanged,
        regardless of HTML noise (CSRF tokens, build hashes, etc.)."""
        canonical = source_url.rstrip("/").lower()
        payload = f"{canonical}|{normalized_text}".encode()
        return sha256(payload).hexdigest()[:32]

    @staticmethod
    def hash_text(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()


class NormalizedDocument(BaseModel):
    metadata: DocumentMetadata
    text: str
