from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractionResult:
    text: str
    title: str | None
    section: str | None
    raw_bytes: bytes
    raw_ext: str  # "pdf" | "html"
    extra: dict[str, Any]


class Extractor(ABC):
    @abstractmethod
    def extract(self, url: str, raw: bytes) -> ExtractionResult: ...
