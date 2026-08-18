from __future__ import annotations

import re
from datetime import datetime

from .models import DateCandidate, OCRPage
from .rules_loader import PlatformRule, RuleSet


NUMERIC_DATE_RE = re.compile(
    r"(?<![0-9O])(?P<year>20[0-9O]{2})\s*[-/.]\s*(?P<month>[0-9O]{1,2})\s*[-/.]\s*"
    r"(?P<day>[0-9O]{1,2})(?:\s+(?P<hour>[0-9O]{1,2})\s*:\s*(?P<minute>[0-9O]{1,2})"
    r"(?:\s*:\s*(?P<second>[0-9O]{1,2}))?)?"
)
CHINESE_DATE_RE = re.compile(
    r"(?<![0-9O])(?P<year>20[0-9O]{2})\s*年\s*(?P<month>[0-9O]{1,2})\s*月\s*"
    r"(?P<day>[0-9O]{1,2})\s*日?(?:\s+(?P<hour>[0-9O]{1,2})\s*:\s*(?P<minute>[0-9O]{1,2})"
    r"(?:\s*:\s*(?P<second>[0-9O]{1,2}))?)?"
)


def _as_int(value: str | None, default: int = 0) -> tuple[int, bool]:
    if value is None:
        return default, False
    corrected = "O" in value.upper()
    return int(value.upper().replace("O", "0")), corrected


def _parse_match(match: re.Match[str]) -> tuple[datetime, bool, bool] | None:
    corrected = False
    values = {}
    for field in ("year", "month", "day", "hour", "minute", "second"):
        values[field], changed = _as_int(match.group(field))
        corrected = corrected or changed
    try:
        parsed = datetime(
            values["year"], values["month"], values["day"], values["hour"], values["minute"], values["second"]
        )
    except ValueError:
        return None
    return parsed, match.group("second") is not None, corrected


def extract_date_candidates(pages: tuple[OCRPage, ...]) -> tuple[DateCandidate, ...]:
    candidates: list[DateCandidate] = []
    seen: set[tuple[int, datetime, tuple[int, ...]]] = set()
    global_offset = 0
    for page in pages:
        blocks = page.blocks
        for start in range(len(blocks)):
            for size in range(1, min(3, len(blocks) - start) + 1):
                selected = blocks[start : start + size]
                for separator in ("", " "):
                    parts = []
                    spans = []
                    cursor = 0
                    for block_index, block in enumerate(selected):
                        if block_index:
                            parts.append(separator)
                            cursor += len(separator)
                        block_start = cursor
                        parts.append(block.normalized_text)
                        cursor += len(block.normalized_text)
                        spans.append((block_start, cursor))
                    combined = "".join(parts)
                    for pattern in (NUMERIC_DATE_RE, CHINESE_DATE_RE):
                        for match in pattern.finditer(combined):
                            parsed = _parse_match(match)
                            if parsed is None:
                                continue
                            local_indexes = tuple(
                                index
                                for index, (span_start, span_end) in enumerate(spans)
                                if span_end > match.start() and span_start < match.end()
                            )
                            indexes = tuple(global_offset + start + index for index in local_indexes)
                            matched_blocks = tuple(selected[index] for index in local_indexes)
                            value, has_seconds, corrected = parsed
                            key = (page.page_index, value, indexes)
                            if key in seen:
                                continue
                            seen.add(key)
                            candidates.append(
                                DateCandidate(
                                    raw_text=match.group(0),
                                    normalized_datetime=value,
                                    label=None,
                                    source_block_indexes=indexes,
                                    page_index=page.page_index,
                                    ocr_confidence=sum(block.confidence for block in matched_blocks) / len(matched_blocks),
                                    has_seconds=has_seconds,
                                    corrected=corrected,
                                )
                            )
        global_offset += len(blocks)
    return tuple(candidates)


def extract_order_number(
    pages: tuple[OCRPage, ...],
    platform_rule: PlatformRule | None,
    rules: RuleSet,
) -> str | None:
    patterns = list(platform_rule.order_number_patterns if platform_rule else ())
    patterns.extend(rules.common["generic_order_number_patterns"])
    for page in pages:
        texts = [block.normalized_text for block in page.blocks]
        searchable = texts + ["".join(texts[index : index + 3]) for index in range(len(texts))]
        for text in searchable:
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)
    return None
