from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .golden_validator import DateValidationSummary, validate_golden_dates


CSV_HEADERS = ("编号", "上传人", "用途（必填）", "税后金额", "发票", "订单截图")


def write_validation_csv(scan_summary_path: Path, output_path: Path) -> int:
    payload = json.loads(scan_summary_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("扫描摘要缺少 files 列表")

    bx_ids = []
    seen = set()
    for item in files:
        bx_id = str(item.get("bx_id", "")).strip().upper()
        if bx_id and bx_id not in seen:
            seen.add(bx_id)
            bx_ids.append(bx_id)
    if not bx_ids:
        raise ValueError("扫描摘要中没有可用的 BX 编号")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for bx_id in bx_ids:
            writer.writerow(
                {
                    "编号": bx_id,
                    "上传人": "P4验证",
                    "用途（必填）": "订单日期全量验证",
                    "税后金额": "",
                    "发票": "",
                    "订单截图": "",
                }
            )
    return len(bx_ids)


def _ratio(summary: DateValidationSummary, rows) -> dict[str, int | float]:
    correct = sum(row.correct for row in rows)
    return {
        "correct": correct,
        "total": len(rows),
        "accuracy": summary.accuracy(rows),
    }

def build_validation_metrics(
    prediction_json: Path,
    golden_workbook: Path,
    elapsed_seconds: float,
) -> dict[str, object]:
    payload = json.loads(prediction_json.read_text(encoding="utf-8"))
    files = payload.get("files", [])
    aggregated = payload.get("aggregated", [])
    golden = validate_golden_dates(prediction_json, golden_workbook)
    status_counts = Counter(str(item.get("status", "UNKNOWN")) for item in files)
    aggregate_status_counts = Counter(str(item.get("status", "UNKNOWN")) for item in aggregated)
    platform_counts = Counter(str(item.get("platform", "unknown")) for item in files)
    errors = [
        {
            "source_file": row.source_file,
            "status": row.status,
            "predicted_date": row.predicted_date.isoformat() if row.predicted_date else None,
            "manual_date": row.manual_date.isoformat() if row.manual_date else None,
        }
        for row in golden.rows
        if not row.correct
    ]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "rule_version": payload.get("rule_version", ""),
        "engine_fingerprint": payload.get("engine_fingerprint", ""),
        "file_count": len(files),
        "aggregate_count": len(aggregated),
        "file_statuses": dict(sorted(status_counts.items())),
        "aggregate_statuses": dict(sorted(aggregate_status_counts.items())),
        "platforms": dict(sorted(platform_counts.items())),
        "golden": {
            "overall": _ratio(golden, golden.rows),
            "dated": _ratio(golden, golden.dated_rows),
            "no_date": _ratio(golden, golden.no_date_rows),
            "auto_accepted": _ratio(golden, golden.auto_accepted_rows),
            "errors": errors,
        },
    }
