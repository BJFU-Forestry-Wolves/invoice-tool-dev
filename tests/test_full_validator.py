import csv
import json
from datetime import datetime

from openpyxl import Workbook

from order_date.full_validator import build_validation_metrics, write_validation_csv


def test_write_validation_csv_deduplicates_bx_ids(tmp_path):
    summary = tmp_path / "scan.json"
    summary.write_text(
        json.dumps({"files": [{"bx_id": "BX002"}, {"bx_id": "bx001"}, {"bx_id": "BX002"}]}),
        encoding="utf-8",
    )
    output = tmp_path / "validation.csv"

    assert write_validation_csv(summary, output) == 2
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["编号"] for row in rows] == ["BX002", "BX001"]
    assert all(row["用途（必填）"] == "订单日期全量验证" for row in rows)


def test_build_validation_metrics_uses_date_only_accuracy(tmp_path):
    predictions = tmp_path / "predictions.json"
    predictions.write_text(
        json.dumps(
            {
                "rule_version": "rules-v1",
                "engine_fingerprint": "engine-v1",
                "files": [
                    {
                        "source_file": "BX001.jpg",
                        "status": "AUTO_ACCEPTED",
                        "platform": "jd",
                        "order_datetime": "2026-08-16T18:30:00",
                    },
                    {
                        "source_file": "BX002.jpg",
                        "status": "NO_ORDER_DATE",
                        "platform": "unknown",
                        "order_datetime": None,
                    },
                ],
                "aggregated": [{"status": "AUTO_ACCEPTED"}, {"status": "NO_ORDER_DATE"}],
            }
        ),
        encoding="utf-8",
    )
    workbook_path = tmp_path / "golden.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "黄金样本标注"
    sheet.append(["源文件", "人工下单时间"])
    sheet.append(["BX001.jpg", datetime(2026, 8, 16, 9, 0, 0)])
    sheet.append(["BX002.jpg", "无日期"])
    workbook.save(workbook_path)

    metrics = build_validation_metrics(predictions, workbook_path, 1.2345)

    assert metrics["file_count"] == 2
    assert metrics["platforms"] == {"jd": 1, "unknown": 1}
    assert metrics["golden"]["overall"] == {"correct": 2, "total": 2, "accuracy": 1.0}
    assert metrics["elapsed_seconds"] == 1.234
