from pathlib import Path

import pytest

from order_date.input_loader import load_expense_records


HEADER = "编号,上传人,用途（必填）,税后金额,发票,订单截图\n"


def test_load_expense_records_normalizes_and_skips_empty_rows(tmp_path: Path):
    path = tmp_path / "input.csv"
    path.write_text(
        HEADER + "BX123,  张　 三  ,差旅,,invoice.pdf,order.png\n" + ",,,,,\n",
        encoding="utf-8-sig",
    )
    skipped = []

    records = load_expense_records(path, lambda row, reason: skipped.append((row, reason)))

    assert len(records) == 1
    assert records[0].bx_id == "BX123"
    assert records[0].uploader == "张 三"
    assert records[0].amount == "未知金额"
    assert skipped == [(3, "编号为空")]


def test_load_expense_records_rejects_missing_columns(tmp_path: Path):
    path = tmp_path / "input.csv"
    path.write_text("编号,上传人\nBX123,A\n", encoding="utf-8")

    with pytest.raises(ValueError, match="缺少必需列"):
        load_expense_records(path)
