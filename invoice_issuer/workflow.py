from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Callable

from order_date.cache_db import OCRCache
from order_date.models import ProcessingResult
from order_date.pipeline import build_engine, fingerprint_without_loading_engine, process_sources, scan_inputs

from .aggregator import LIMIT, aggregate_daily_merchants
from .excel_report import write_invoice_issuer_report
from .extractor import EXTRACTOR_VERSION, extract_invoice_issuer
from .manifest_loader import load_invoice_contexts
from .models import InvoiceIssuerResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_MANIFEST = PROJECT_ROOT / "models" / "manifest.json"
ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class WorkflowOptions:
    manifest_path: Path
    attach_root: Path
    output_dir: Path
    cache_path: Path | None = None
    models_dir: Path | None = None
    cpu_threads: int = max(1, min(4, os.cpu_count() or 1))
    force_reprocess: bool = False
    limit: int | None = None
    daily_limit: Decimal = LIMIT


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    result_json_path: Path
    report_path: Path
    total_files: int
    accepted: int
    review: int
    failed: int
    daily_groups: int
    exceeded_groups: int


def _outside_repository(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved == PROJECT_ROOT or resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"{label}必须位于 Git 仓库外: {resolved}")
    return resolved


def _emit(callback: ProgressCallback | None, **payload: object) -> None:
    if callback:
        callback(payload)


def _serialize(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def run_invoice_issuer_workflow(
    options: WorkflowOptions,
    progress_callback: ProgressCallback | None = None,
) -> WorkflowResult:
    started = perf_counter()
    manifest_path = options.manifest_path.resolve()
    attach_root = options.attach_root.resolve()
    output_dir = _outside_repository(options.output_dir, "结果目录")
    cache_path = _outside_repository(options.cache_path or output_dir / ".invoice_issuer_cache.sqlite3", "缓存文件")
    models_dir = options.models_dir or (
        Path(os.environ["LOCALAPPDATA"]) / "InvoiceAttachmentTool" / "models"
        if os.environ.get("LOCALAPPDATA")
        else PROJECT_ROOT / ".paddlex-model-cache"
    )

    contexts = load_invoice_contexts(manifest_path)
    bx_ids = {context.bx_id for values in contexts.values() for context in values if context.bx_id}
    _emit(progress_callback, stage="scan", current=0, total=0, current_file="")
    scan = scan_inputs(attach_root / "发票", bx_ids=bx_ids, limit=options.limit)
    fingerprint = fingerprint_without_loading_engine(MODEL_MANIFEST)
    _emit(progress_callback, stage="scan", current=len(scan.files), total=len(scan.files), current_file="")

    with OCRCache(cache_path) as cache:
        needs_engine = options.force_reprocess or any(cache.get(source.file_hash, fingerprint) is None for source in scan.files)
        engine = build_engine(models_dir, MODEL_MANIFEST, options.cpu_threads) if needs_engine else None

        def ocr_progress(current: int, total: int, result: ProcessingResult) -> None:
            _emit(progress_callback, stage="ocr", current=current, total=total, current_file=result.source.relative_path)

        processing = process_sources(
            scan.files,
            cache,
            fingerprint,
            engine,
            force=options.force_reprocess,
            on_progress=ocr_progress,
        )

    results: list[InvoiceIssuerResult] = []
    counters = Counter()
    for current, item in enumerate(processing, start=1):
        if item.status == "OCR_FAILED" or item.cached_status == "OCR_FAILED":
            result = InvoiceIssuerResult(
                item.source.bx_id,
                item.source.relative_path,
                item.source.file_hash,
                None,
                None,
                0.0,
                "OCR_FAILED",
                item.error_message or "OCR 失败",
                0,
                error_code=item.error_code or "OCR_PREDICT_FAILED",
            )
        else:
            result = extract_invoice_issuer(
                item.source.bx_id,
                item.source.relative_path,
                item.source.file_hash,
                item.pages,
            )
        results.append(result)
        counters[result.status] += 1
        _emit(
            progress_callback,
            stage="extract",
            current=current,
            total=len(processing),
            current_file=item.source.relative_path,
            accepted=counters["AUTO_ACCEPTED"],
            review=counters["NEEDS_REVIEW"] + counters["NO_ISSUER"],
            failed=counters["OCR_FAILED"],
        )

    result_tuple = tuple(results)
    groups, review_items = aggregate_daily_merchants(result_tuple, contexts, options.daily_limit)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_json_path = output_dir / f"发票开票公司识别结果_{timestamp}.json"
    payload = {
        "schema_version": "1",
        "extractor_version": EXTRACTOR_VERSION,
        "engine_fingerprint": fingerprint,
        "daily_limit": str(options.daily_limit),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "total_files": len(result_tuple),
            "auto_accepted": counters["AUTO_ACCEPTED"],
            "needs_review": counters["NEEDS_REVIEW"] + counters["NO_ISSUER"],
            "ignored_non_invoice": counters["NOT_INVOICE"],
            "ocr_failed": counters["OCR_FAILED"],
            "daily_groups": len(groups),
            "exceeded_groups": sum(group.status == "EXCEEDED" for group in groups),
            "aggregation_review_items": len(review_items),
            "ocr_cache_hits": sum(item.cache_hit for item in processing),
            "scan_issues": len(scan.issues),
            "elapsed_seconds": round(perf_counter() - started, 3),
        },
        "files": [_serialize(asdict(item)) for item in result_tuple],
        "daily_groups": [_serialize(asdict(item)) for item in groups],
        "review_items": [_serialize(asdict(item)) for item in review_items],
        "scan_issues": [_serialize(asdict(item)) for item in scan.issues],
    }
    result_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = output_dir / f"发票开票公司识别报告_{timestamp}.xlsx"
    write_invoice_issuer_report(
        report_path,
        groups=groups,
        results=result_tuple,
        review_items=review_items,
        daily_limit=options.daily_limit,
        stats=payload["stats"],
    )
    _emit(progress_callback, stage="done", current=len(result_tuple), total=len(result_tuple), current_file=result_json_path.name)
    return WorkflowResult(
        result_json_path,
        report_path,
        len(result_tuple),
        counters["AUTO_ACCEPTED"],
        counters["NEEDS_REVIEW"] + counters["NO_ISSUER"],
        counters["OCR_FAILED"],
        len(groups),
        sum(group.status == "EXCEEDED" for group in groups),
    )
