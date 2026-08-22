from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InvoiceIssuerResult:
    bx_id: str
    source_file: str
    file_hash: str
    issuer_name: str | None
    normalized_issuer: str | None
    confidence_score: float
    status: str
    evidence_text: str
    candidate_count: int
    page_index: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class InvoiceContext:
    bx_id: str
    source_path: str
    order_date: date | None
    amount: Decimal | None
    uploader: str
    purpose: str


@dataclass(frozen=True, slots=True)
class DailyMerchantGroup:
    order_date: date
    issuer_name: str
    normalized_issuer: str
    total_amount: Decimal
    status: str
    bx_ids: tuple[str, ...]
    source_files: tuple[str, ...]
    evidence_text: str


@dataclass(frozen=True, slots=True)
class ReviewItem:
    bx_id: str
    source_files: tuple[str, ...]
    reason: str
    issuer_names: tuple[str, ...] = ()
    order_dates: tuple[date, ...] = ()
    amount: Decimal | None = None
