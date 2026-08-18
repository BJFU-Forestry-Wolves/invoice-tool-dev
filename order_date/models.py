from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class PlatformDetection:
    platform: str
    display_name: str
    score: float
    positive_hits: tuple[str, ...]
    negative_hits: tuple[str, ...]
    rule_version: str


@dataclass(frozen=True, slots=True)
class DateCandidate:
    raw_text: str
    normalized_datetime: datetime
    label: str | None
    source_block_indexes: tuple[int, ...]
    page_index: int
    ocr_confidence: float
    has_seconds: bool
    corrected: bool


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: DateCandidate
    score: float
    reasons: tuple[str, ...]
    negative_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    bx_id: str
    source_file: str
    file_hash: str
    platform: str
    platform_score: float
    order_number: str | None
    order_datetime: datetime | None
    confidence_score: float
    status: str
    evidence_text: str
    rule_version: str
    candidate_count: int
    page_index: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class AggregatedResult:
    bx_id: str
    order_number: str | None
    order_datetime: datetime | None
    confidence_score: float
    status: str
    source_files: tuple[str, ...]
    evidence_text: str
    rule_version: str
