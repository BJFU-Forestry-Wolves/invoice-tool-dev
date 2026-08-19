import json
from datetime import datetime

from openpyxl import Workbook

from order_date.golden_validator import validate_golden_dates


def test_golden_validator_compares_calendar_date_only(tmp_path):
    predictions = tmp_path / "predictions.json"
    predictions.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "source_file": "sample-a.jpg",
                        "order_datetime": "2026-04-16T22:58:57",
                        "status": "AUTO_ACCEPTED",
                    },
                    {
                        "source_file": "sample-b.jpg",
                        "order_datetime": None,
                        "status": "NO_ORDER_DATE",
                    },
                    {
                        "source_file": "sample-c.jpg",
                        "order_datetime": "2026-04-09T09:00:00",
                        "status": "NEEDS_REVIEW",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    workbook_path = tmp_path / "golden.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "黄金样本标注"
    sheet.append(["标题", None])
    sheet.append(["说明", None])
    sheet.append(["编号样本文件", "人工下单时间"])
    sheet.append(["001_sample-a.jpg", datetime(2026, 4, 16, 1, 2, 3)])
    sheet.append(["002_sample-b.jpg", "附件内未显示"])
    sheet.append(["003_sample-c.jpg", datetime(2026, 4, 8, 23, 59, 59)])
    workbook.save(workbook_path)

    summary = validate_golden_dates(predictions, workbook_path)

    assert summary.total == 3
    assert summary.correct == 2
    assert summary.accuracy(summary.dated_rows) == 0.5
    assert summary.accuracy(summary.no_date_rows) == 1.0
    assert summary.accuracy(summary.auto_accepted_rows) == 1.0
