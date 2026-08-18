from __future__ import annotations

import argparse
import json
from collections import Counter
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from order_date.aggregator import aggregate_bx_results
from order_date.cache_db import OCRCache
from order_date.extractor import extract_order_date
from order_date.models import ExtractionResult
from order_date.pipeline import fingerprint_without_loading_engine, scan_inputs
from order_date.rules_loader import load_rules
from order_date_cli import MODEL_MANIFEST, PROJECT_ROOT, configure_console_encoding, ensure_outside_repository


RULES_DIR = PROJECT_ROOT / "order_date" / "rules"


def materialize_source_result(
    result: ExtractionResult,
    bx_id: str,
    source_file: str,
    duplicate: bool,
) -> ExtractionResult:
    result = replace(result, bx_id=bx_id, source_file=source_file)
    if duplicate:
        result = replace(
            result,
            status="DUPLICATE",
            evidence_text=result.evidence_text + "; 内容哈希与前序附件相同",
        )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="订单日期平台与规则提取（P2）")
    parser.add_argument("--attach-root", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="仓库外 JSON 规则结果")
    parser.add_argument("--golden-output", type=Path, help="仓库外人工标注工作簿")
    parser.add_argument("--golden-size", type=int, default=100)
    parser.add_argument("--reimbursement-date", type=date.fromisoformat)
    parser.add_argument("--force-rules", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _write_golden(path: Path, results: tuple[ExtractionResult, ...], size: int) -> None:
    strata = defaultdict(list)
    for result in sorted(results, key=lambda item: item.file_hash):
        strata[(result.platform, result.status)].append(result)
    selected = []
    while len(selected) < size and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(selected) < size:
                selected.append(strata[key].pop(0))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "黄金样本标注"
    sheet.append(
        [
            "源文件",
            "BX编号",
            "预测平台",
            "预测订单号",
            "预测下单时间",
            "预测分数",
            "预测状态",
            "规则证据",
            "人工平台",
            "人工订单号",
            "人工下单时间",
            "人工结论",
            "备注",
        ]
    )
    for result in selected:
        sheet.append(
            [
                result.source_file,
                result.bx_id,
                result.platform,
                result.order_number,
                result.order_datetime,
                result.confidence_score,
                result.status,
                result.evidence_text,
                "",
                "",
                "",
                "",
                "",
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = parse_args(argv)
    output = ensure_outside_repository(args.output, "规则结果")
    cache_path = ensure_outside_repository(args.cache, "缓存文件")
    golden_output = ensure_outside_repository(args.golden_output, "黄金样本") if args.golden_output else None
    rules = load_rules(RULES_DIR)
    scan = scan_inputs(args.attach_root.resolve() / "订单截图")
    fingerprint = fingerprint_without_loading_engine(MODEL_MANIFEST)
    results = []
    seen_hashes: set[str] = set()
    rule_cache_hits = 0
    missing_ocr = 0
    with OCRCache(cache_path) as cache:
        for source in scan.files:
            duplicate = source.file_hash in seen_hashes
            seen_hashes.add(source.file_hash)
            cached = None if args.force_rules else cache.get_extraction(source.file_hash, source.bx_id, rules.version)
            if cached is not None:
                results.append(materialize_source_result(cached, source.bx_id, source.relative_path, duplicate))
                rule_cache_hits += 1
                continue
            ocr = cache.get(source.file_hash, fingerprint)
            if ocr is None or ocr.status != "OCR_SUCCEEDED":
                missing_ocr += 1
                result = ExtractionResult(
                    source.bx_id,
                    source.relative_path,
                    source.file_hash,
                    "unknown",
                    0.0,
                    None,
                    None,
                    0.0,
                    "OCR_FAILED",
                    "缺少当前版本 OCR 缓存",
                    rules.version,
                    0,
                    error_code="OCR_CACHE_MISSING",
                )
            else:
                result = extract_order_date(
                    source.bx_id,
                    source.relative_path,
                    source.file_hash,
                    ocr.pages,
                    rules,
                    args.reimbursement_date,
                )
            cache.store_extraction(result)
            results.append(materialize_source_result(result, source.bx_id, source.relative_path, duplicate))

    result_tuple = tuple(results)
    aggregated = aggregate_bx_results(result_tuple, rules)
    platform_counts = Counter(result.platform for result in result_tuple)
    status_counts = Counter(result.status for result in result_tuple)
    aggregate_status_counts = Counter(result.status for result in aggregated)
    if not args.quiet:
        print(f"规则版本: {rules.version}")
    print(f"文件结果: {dict(sorted(status_counts.items()))}")
    print(f"平台分布: {dict(sorted(platform_counts.items()))}")
    print(f"聚合结果: {dict(sorted(aggregate_status_counts.items()))}")
    print(f"规则缓存命中: {rule_cache_hits}/{len(result_tuple)}, OCR缓存缺失: {missing_ocr}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "rule_version": rules.version,
                "file_statuses": dict(status_counts),
                "platforms": dict(platform_counts),
                "aggregate_statuses": dict(aggregate_status_counts),
                "rule_cache_hits": rule_cache_hits,
                "ocr_cache_missing": missing_ocr,
                "files": [
                    {
                        **asdict(result),
                        "order_datetime": result.order_datetime.isoformat() if result.order_datetime else None,
                    }
                    for result in result_tuple
                ],
                "aggregated": [
                    {
                        **asdict(result),
                        "order_datetime": result.order_datetime.isoformat() if result.order_datetime else None,
                    }
                    for result in aggregated
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if golden_output:
        _write_golden(golden_output, result_tuple, min(args.golden_size, len(result_tuple)))
    return 1 if missing_ocr else 0


if __name__ == "__main__":
    raise SystemExit(main())
