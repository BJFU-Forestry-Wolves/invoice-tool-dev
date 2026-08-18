from __future__ import annotations

from dataclasses import dataclass


Point = tuple[float, float]
Polygon = tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class OCRTextBlock:
    """Version-independent OCR text with auditable source text and geometry."""

    text: str
    normalized_text: str
    confidence: float
    polygon: Polygon
    page_index: int

