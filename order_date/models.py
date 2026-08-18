from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


Point = tuple[float, float]
Polygon = tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class ExpenseRecord:
    bx_id: str
    uploader: str
    purpose: str
    amount: str
    invoice_filename: str
    order_filename: str
    row_number: int

    def as_legacy_dict(self) -> dict[str, str]:
        return {
            "unique_id": self.bx_id,
            "uploader": self.uploader,
            "purpose": self.purpose,
            "amount": self.amount,
            "invoice_filename": self.invoice_filename,
            "order_filename": self.order_filename,
        }


@dataclass(frozen=True, slots=True)
class SourceFile:
    bx_id: str
    path: Path
    relative_path: str
    file_hash: str
    extension: str
    file_size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class OCRTextBlock:
    """Version-independent OCR text with auditable source text and geometry."""

    text: str
    normalized_text: str
    confidence: float
    polygon: Polygon
    page_index: int


@dataclass(frozen=True, slots=True)
class OCRPage:
    page_index: int
    blocks: tuple[OCRTextBlock, ...]


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    source: SourceFile
    status: str
    pages: tuple[OCRPage, ...] = ()
    cache_hit: bool = False
    cached_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
