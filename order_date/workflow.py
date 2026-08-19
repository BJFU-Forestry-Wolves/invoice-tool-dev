from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from .aggregator import aggregate_bx_results
from .cache_db import OCRCache
from .excel_report import ReportRunStats, write_excel_report
from .extractor import extract_order_date
from .input_loader import load_expense_records
from .models import ExtractionResult, ProcessingResult
from .pipeline import build_engine, fingerprint_without_loading_engine, process_sources, scan_inputs
from .rules_loader import load_rules


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_MANIFEST = PROJECT_ROOT / "models" / "manifest.json"
RULES_DIR = PROJECT_ROOT / "order_date" / "rules"
ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class WorkflowOptions:
    csv_path: Path
    attach_root: Path
    output_dir: Path
    cache_path: Path | None = None
    models_dir: Path | None = None
    cpu_threads: int = max(1, min(4, os.cpu_count() or 1))
    force_reprocess: bool = False
    reimbursement_date: date | None = None


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    report_path: Path
    result_json_path: Path
    total_files: int
    accepted: int
    review: int
    failed: int


def _outside_repository(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved == PROJECT_ROOT or resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"{label}必须位于 Git 仓库外: {resolved}")
    return resolved


def _emit(callback: ProgressCallback | None, **payload: object) -> None:
    if callback:
        callback(payload)


def _materialize(result: ExtractionResult, source_file: str, duplicate: bool) -> ExtractionResult:
    value = replace(result, source_file=source_file)
    if duplicate:
        value = replace(value, status="DUPLICATE", evidence_text=value.evidence_text + "; 内容哈希与前序附件相同")
    return value


def run_order_date_workflow(
    options: WorkflowOptions,
    progress_callback: ProgressCallback | None = None,
) -> WorkflowResult:
    started = perf_counter()
    csv_path = options.csv_path.resolve()
    attach_root = options.attach_root.resolve()
    output_dir = _outside_repository(options.output_dir, "结果目录")
    cache_path = _outside_repository(options.cache_path or output_dir / ".order_date_cache.sqlite3", "缓存文件")
    models_dir = options.models_dir or (Path(os.environ["LOCALAPPDATA"]) / "InvoiceAttachmentTool" / "models" if os.environ.get("LOCALAPPDATA") else PROJECT_ROOT / ".paddlex-model-cache")
    records = load_expense_records(csv_path)
    bx_ids = {record.bx_id.upper() for record in records}

    _emit(progress_callback, stage="scan", current=0, total=0, current_file="")
    scan = scan_inputs(attach_root / "订单截图", bx_ids=bx_ids)
    fingerprint = fingerprint_without_loading_engine(MODEL_MANIFEST)
    rules = load_rules(RULES_DIR)
    _emit(progress_callback, stage="scan", current=len(scan.files), total=len(scan.files), current_file="")

    with OCRCache(cache_path) as cache:
        needs_engine = options.force_reprocess or any(cache.get(source.file_hash, fingerprint) is None for source in scan.files)
        engine = build_engine(models_dir, MODEL_MANIFEST, options.cpu_threads) if needs_engine else None

        def ocr_progress(current: int, total: int, result: ProcessingResult) -> None:
            _emit(
                progress_callback,
                stage="ocr",
                current=current,
                total=total,
                current_file=result.source.relative_path,
            )

        processing = process_sources(
            scan.files,
            cache,
            fingerprint,
            engine,
            force=options.force_reprocess,
            on_progress=ocr_progress,
        )
        pages_by_hash = {item.source.file_hash: item.pages for item in processing if item.pages}
        ocr_cache_hit_hashes = frozenset(item.source.file_hash for item in processing if item.cache_hit)
        results = []
        seen_hashes = set()
        rule_cache_hits = 0
        processing_seconds = {}
        counters = Counter()
        for current, item in enumerate(processing, start=1):
            step_started = perf_counter()
            duplicate = item.source.file_hash in seen_hashes
            seen_hashes.add(item.source.file_hash)
            cached_extraction = None if options.force_reprocess else cache.get_extraction(
                item.source.file_hash, item.source.bx_id, rules.version
            )
            if cached_extraction is not None:
                base_result = cached_extraction
                rule_cache_hits += 1
            elif item.status == "OCR_FAILED" or item.cached_status == "OCR_FAILED":
                base_result = ExtractionResult(
                    item.source.bx_id,
                    item.source.relative_path,
                    item.source.file_hash,
                    "unknown",
                    0.0,
                    None,
                    None,
                    0.0,
                    "OCR_FAILED",
                    item.error_message or "OCR 失败",
                    rules.version,
                    0,
                    error_code=item.error_code or "OCR_PREDICT_FAILED",
                )
            else:
                base_result = extract_order_date(
                    item.source.bx_id,
                    item.source.relative_path,
                    item.source.file_hash,
                    item.pages,
                    rules,
                    options.reimbursement_date,
                )
                cache.store_extraction(base_result)
            result = _materialize(base_result, item.source.relative_path, duplicate)
            results.append(result)
            processing_seconds[item.source.relative_path] = perf_counter() - step_started
            counters[result.status] += 1
            _emit(
                progress_callback,
                stage="rules",
                current=current,
                total=len(processing),
                current_file=item.source.relative_path,
                accepted=counters["AUTO_ACCEPTED"],
                review=counters["NEEDS_REVIEW"] + counters["NO_ORDER_DATE"] + counters["CONFLICT"],
                failed=counters["OCR_FAILED"],
            )

    result_tuple = tuple(results)
    aggregated = aggregate_bx_results(result_tuple, rules)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_json_path = output_dir / f"订单日期规则结果_{timestamp}.json"
    result_json_path.write_text(
        json.dumps(
            {
                "rule_version": rules.version,
                "engine_fingerprint": fingerprint,
                "files": [
                    {**asdict(result), "order_datetime": result.order_datetime.isoformat() if result.order_datetime else None}
                    for result in result_tuple
                ],
                "aggregated": [
                    {**asdict(result), "order_datetime": result.order_datetime.isoformat() if result.order_datetime else None}
                    for result in aggregated
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _emit(progress_callback, stage="excel", current=0, total=1, current_file="")
    report_path = write_excel_report(
        output_dir / f"订单下单日期识别结果_{timestamp}.xlsx",
        records,
        scan.files,
        result_tuple,
        aggregated,
        pages_by_hash,
        ocr_cache_hit_hashes,
        processing_seconds,
        ReportRunStats(
            rule_cache_hits=rule_cache_hits,
            ocr_cache_hits=sum(1 for item in processing if item.cache_hit),
            elapsed_seconds=perf_counter() - started,
            engine_fingerprint=fingerprint,
            scan_issue_count=len(scan.issues),
        ),
    )
    _emit(progress_callback, stage="excel", current=1, total=1, current_file=report_path.name)
    review_count = counters["NEEDS_REVIEW"] + counters["NO_ORDER_DATE"] + counters["CONFLICT"]
    return WorkflowResult(
        report_path=report_path,
        result_json_path=result_json_path,
        total_files=len(result_tuple),
        accepted=counters["AUTO_ACCEPTED"],
        review=review_count,
        failed=counters["OCR_FAILED"],
    )
