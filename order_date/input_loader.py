from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from .models import ExpenseRecord


REQUIRED_COLUMNS = {
    "编号": "bx_id",
    "上传人": "uploader",
    "用途（必填）": "purpose",
    "税后金额": "amount",
    "发票": "invoice_filename",
    "订单截图": "order_filename",
}


def normalize_uploader(name: object) -> str:
    if name is None:
        return "未知上传者"
    normalized = str(name).replace("　", " ").strip()
    return " ".join(normalized.split()) or "未知上传者"


def load_expense_records(
    path: Path,
    on_skip: Callable[[int, str], None] | None = None,
) -> tuple[ExpenseRecord, ...]:
    records: list[ExpenseRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("CSV 中没有表头。")
        reader.fieldnames = [str(column).strip() for column in reader.fieldnames]
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV 缺少必需列: {sorted(missing)}")

        for row_number, row in enumerate(reader, start=2):
            normalized = {
                str(key).strip(): "" if value is None else str(value).strip()
                for key, value in row.items()
                if key is not None
            }
            values = {field: normalized.get(column, "") for column, field in REQUIRED_COLUMNS.items()}
            if not values["bx_id"]:
                if on_skip:
                    on_skip(row_number, "编号为空")
                continue
            if not any(values[field] for field in values if field != "bx_id"):
                if on_skip:
                    on_skip(row_number, "除编号外均为空")
                continue
            records.append(
                ExpenseRecord(
                    bx_id=values["bx_id"],
                    uploader=normalize_uploader(values["uploader"]),
                    purpose=values["purpose"],
                    amount=values["amount"] or "未知金额",
                    invoice_filename=values["invoice_filename"],
                    order_filename=values["order_filename"],
                    row_number=row_number,
                )
            )
    return tuple(records)
