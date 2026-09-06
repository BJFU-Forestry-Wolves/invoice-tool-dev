import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from classify_attachments import build_plan
from rename_invoices_orders import render_target_filename, validate_name_template


MASTER_HEADERS = [
    "编号", "日期", "发票", "开票日期", "发票类型", "税后金额", "用途（必填）",
    "发票单号后四位", "订单截图", "需要补充订单", "是否已报销", "是否A钱",
    "A钱人员", "报销方式", "发票报销类型", "是否需要修改发票文件", "上传人",
]


def write_master(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "发票记录"
    sheet.append(MASTER_HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def write_manual(path: Path, source: str, value: object) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "黄金样本标注"
    sheet.append(["标题"])
    sheet.append(["说明"])
    sheet.append(["编号样本文件", "BX编号", "预测平台", "预测订单号", "预测下单时间", "预测分数",
                  "预测状态", "规则证据", "人工平台", "人工订单号", "人工下单时间", "人工结论", "备注"])
    sheet.append([source, "BX1", "", "", "", "", "", "", "", "", value, "", ""])
    workbook.save(path)


def master_row(bx_id: str, invoice: str, order: str, uploader: str = "测试人员",
               amount: str = "12.50") -> list[object]:
    values = {"编号": bx_id, "发票": invoice, "订单截图": order, "税后金额": amount,
              "用途（必填）": "测试用途", "上传人": uploader}
    return [values.get(header, "") for header in MASTER_HEADERS]


def test_order_date_placeholder_is_supported():
    template = validate_name_template("{下单日期}_{编号}_{附件标记}")
    result = render_target_filename(template, "BX1", "甲", "用途", "1", "发票", 1, 1, ".pdf",
                                    order_date="2026-01-02")
    assert result == "2026-01-02_BX1_发票.pdf"


def test_manual_date_overrides_rule_date(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    (attach / "发票" / "BX1.pdf").write_bytes(b"invoice")
    (attach / "订单截图" / "BX1.jpg").write_bytes(b"order")
    write_master(master, [master_row("BX1", "invoice.pdf", "order.jpg")])
    write_manual(manual, "001_BX1.jpg", datetime(2026, 1, 2, 9, 0))
    rules.write_text(json.dumps({"files": [{"source_file": "BX1.jpg", "order_datetime": "2026-01-03T10:00:00",
                                             "status": "AUTO_ACCEPTED", "evidence_text": "rule"}]}), encoding="utf-8")

    plan = build_plan(master, attach, rules, manual, reference, tmp_path / "output")

    assert plan["stats"]["records"] == 1
    assert plan["stats"]["anomaly_records"] == 0
    assert any(entry["dimension"] == "日期" and entry["order_date"] == "2026-01-02" for entry in plan["copies"])
    assert not any(entry["order_date"] == "2026-01-03" for entry in plan["copies"])


def test_missing_order_uses_reference_invoice_and_is_anomaly(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    (reference / "new.pdf").write_bytes(b"new invoice")
    write_master(master, [master_row("BX2", "new.pdf", "missing.jpg", uploader="测试人员乙", amount="200.01")])
    write_manual(manual, "001_UNUSED.jpg", "附件内未显示")
    rules.write_text('{"files": []}', encoding="utf-8")

    plan = build_plan(master, attach, rules, manual, reference, tmp_path / "output")

    assert plan["stats"]["anomaly_records"] == 1
    assert plan["anomalies"][0]["primary_category"] == "附件缺失"
    assert not any(entry["dimension"] == "日期" for entry in plan["copies"])
    assert any(entry["dimension"] == "人员" and entry["attachment_type"] == "发票" for entry in plan["copies"])
    assert any(entry["dimension"] == "异常" and entry["attachment_type"] == "发票" for entry in plan["copies"])


def test_low_value_record_only_requires_invoice(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    (reference / "low.pdf").write_bytes(b"low value invoice")
    write_master(master, [master_row("BX3", "low.pdf", "missing.jpg", amount="200")])
    write_manual(manual, "001_UNUSED.jpg", "附件内未显示")
    rules.write_text('{"files": []}', encoding="utf-8")

    plan = build_plan(master, attach, rules, manual, reference, tmp_path / "output")

    assert plan["stats"]["anomaly_records"] == 0
    assert plan["stats"]["invoice_only_records"] == 1
    assert plan["records"][0]["invoice_only_exempt"] is True
    assert not any(entry["dimension"] in {"日期", "异常"} for entry in plan["copies"])
    person_invoice = next(entry for entry in plan["copies"] if entry["dimension"] == "人员")
    assert "低额免订单截图" in person_invoice["target_path"]
    assert person_invoice["status"] == "免订单"


def test_excluded_empty_order_is_removed_from_records_and_anomalies(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    write_master(master, [master_row("BX_EMPTY", "", "", amount="0")])
    write_manual(manual, "001_UNUSED.jpg", "附件内未显示")
    rules.write_text('{"files": []}', encoding="utf-8")

    plan = build_plan(
        master, attach, rules, manual, reference, tmp_path / "output", exclude_ids={"bx_empty"}
    )

    assert plan["stats"]["records"] == 0
    assert plan["stats"]["excluded_records"] == 1
    assert plan["inputs"]["excluded_ids"] == ["BX_EMPTY"]
    assert plan["records"] == []
    assert plan["anomalies"] == []
    assert plan["copies"] == []


def test_resolved_manual_review_overrides_missing_order_and_date(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    review_json = tmp_path / "review.json"
    correction = tmp_path / "correction"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    correction.mkdir()
    (correction / "修正_BX4_发票.pdf").write_bytes(b"corrected")
    write_master(master, [master_row("BX4", "missing.pdf", "missing.jpg", amount="500")])
    write_manual(manual, "001_UNUSED.jpg", "附件内未显示")
    rules.write_text('{"files": []}', encoding="utf-8")
    review_json.write_text(json.dumps({"records": [{
        "bx_id": "BX4", "review_status": "已修正", "confirmed_order_date": "2026-04-01",
        "correction_dir": str(correction), "correction_files": ["修正_BX4_发票.pdf"], "notes": "无订单例外",
    }]}), encoding="utf-8")

    plan = build_plan(master, attach, rules, manual, reference, tmp_path / "output",
                      manual_review_json=review_json)

    assert plan["stats"]["records"] == 1
    assert plan["stats"]["anomaly_records"] == 0
    assert any(entry["dimension"] == "日期" and entry["order_date"] == "2026-04-01"
               for entry in plan["copies"])
    assert plan["records"][0]["manual_review_status"] == "已修正"


def test_void_manual_review_goes_only_to_special_output(tmp_path: Path):
    master = tmp_path / "master.xlsx"
    manual = tmp_path / "manual.xlsx"
    rules = tmp_path / "rules.json"
    review_json = tmp_path / "review.json"
    correction = tmp_path / "correction"
    reference = tmp_path / "reference"
    attach = tmp_path / "attachments"
    (attach / "发票").mkdir(parents=True)
    (attach / "订单截图").mkdir()
    reference.mkdir()
    correction.mkdir()
    (correction / "BX5_发票.pdf").write_bytes(b"void")
    write_master(master, [master_row("BX5", "missing.pdf", "", amount="500")])
    write_manual(manual, "001_UNUSED.jpg", "附件内未显示")
    rules.write_text('{"files": []}', encoding="utf-8")
    review_json.write_text(json.dumps({"records": [{
        "bx_id": "BX5", "review_status": "作废排除", "correction_dir": str(correction),
        "correction_files": ["BX5_发票.pdf"], "notes": "已经提交",
    }]}), encoding="utf-8")

    plan = build_plan(master, attach, rules, manual, reference, tmp_path / "output",
                      manual_review_json=review_json)

    assert plan["stats"]["records"] == 0
    assert plan["stats"]["manual_excluded_records"] == 1
    assert plan["anomalies"] == []
    assert {entry["dimension"] for entry in plan["copies"]} == {"特殊处理"}
    assert "作废排除" in plan["copies"][0]["target_path"]
