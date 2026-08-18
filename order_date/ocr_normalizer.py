from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from .models import OCRTextBlock, Polygon


class OCRNormalizationError(ValueError):
    """Raised when PaddleOCR output cannot be converted without data loss."""


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


def _polygon(value: Any) -> Polygon:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise OCRNormalizationError("OCR polygon is not a coordinate sequence")
    try:
        points = tuple((float(point[0]), float(point[1])) for point in value)
    except (IndexError, TypeError, ValueError) as exc:
        raise OCRNormalizationError("OCR polygon contains invalid coordinates") from exc
    if len(points) < 4:
        raise OCRNormalizationError("OCR polygon must contain at least four points")
    return points


def normalize_page(result: Mapping[str, Any], default_page_index: int = 0) -> tuple[OCRTextBlock, ...]:
    texts = result.get("rec_texts", ())
    scores = result.get("rec_scores", ())
    polygons = result.get("rec_polys", ())
    if not (isinstance(texts, Sequence) and isinstance(scores, Sequence) and isinstance(polygons, Sequence)):
        raise OCRNormalizationError("OCR result fields must be sequences")
    if len(texts) != len(scores) or len(texts) != len(polygons):
        raise OCRNormalizationError(
            f"OCR result length mismatch: texts={len(texts)}, scores={len(scores)}, polygons={len(polygons)}"
        )

    raw_page_index = result.get("page_index")
    page_index = default_page_index if raw_page_index is None else int(raw_page_index)
    blocks: list[OCRTextBlock] = []
    for text, score, polygon in zip(texts, scores, polygons, strict=True):
        original = str(text)
        normalized = normalize_text(original)
        if not normalized:
            continue
        blocks.append(
            OCRTextBlock(
                text=original,
                normalized_text=normalized,
                confidence=float(score),
                polygon=_polygon(polygon),
                page_index=page_index,
            )
        )
    return tuple(blocks)

