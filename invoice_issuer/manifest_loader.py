from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import InvoiceContext


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _amount(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def load_invoice_contexts(manifest_path: Path) -> dict[str, tuple[InvoiceContext, ...]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    contexts: dict[str, list[InvoiceContext]] = defaultdict(list)
    seen: set[tuple[str, str, str | None]] = set()
    for item in payload.get("copies", []):
        if item.get("dimension") != "人员" or item.get("attachment_type") != "发票":
            continue
        source_path = str(Path(item["source_path"]).resolve())
        key = (source_path.casefold(), str(item.get("bx_id", "")).upper(), item.get("order_date"))
        if key in seen:
            continue
        seen.add(key)
        context = InvoiceContext(
            bx_id=str(item.get("bx_id", "")).upper(),
            source_path=source_path,
            order_date=_date(item.get("order_date")),
            amount=_amount(item.get("amount")),
            uploader=str(item.get("uploader", "")),
            purpose=str(item.get("purpose", "")),
        )
        contexts[source_path.casefold()].append(context)
    result = {key: tuple(value) for key, value in contexts.items()}
    for values in tuple(result.values()):
        filename_key = Path(values[0].source_path).name.casefold()
        existing = result.get(filename_key, ())
        result[filename_key] = tuple(dict.fromkeys((*existing, *values)))
    return result
