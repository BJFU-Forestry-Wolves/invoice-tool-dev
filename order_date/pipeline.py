from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .cache_db import OCRCache
from .file_grouper import ScanResult, scan_order_files
from .models import OCRPage, ProcessingResult, SourceFile
from .ocr_engine import PaddleOCREngine, engine_fingerprint


class OCREngine(Protocol):
    fingerprint: str

    def predict(self, path: Path) -> tuple[OCRPage, ...]: ...


def process_sources(
    sources: tuple[SourceFile, ...],
    cache: OCRCache,
    engine_fingerprint_value: str,
    engine: OCREngine | None,
    force: bool = False,
    on_progress: Callable[[int, int, ProcessingResult], None] | None = None,
) -> tuple[ProcessingResult, ...]:
    results: list[ProcessingResult] = []
    total = len(sources)
    for current, source in enumerate(sources, start=1):
        cached = None if force else cache.get(source.file_hash, engine_fingerprint_value)
        if cached is not None:
            result = ProcessingResult(
                source=source,
                status="SKIPPED_CACHE",
                pages=cached.pages,
                cache_hit=True,
                cached_status=cached.status,
                error_code=cached.error_code,
                error_message=cached.error_message,
            )
            results.append(result)
            if on_progress:
                on_progress(current, total, result)
            continue
        if engine is None:
            raise RuntimeError("存在未缓存文件，但 OCR 引擎尚未初始化")
        try:
            pages = engine.predict(source.path)
        except Exception as exc:
            error_code = "OCR_PREDICT_FAILED"
            message = f"{type(exc).__name__}: {exc}"
            cache.store_failure(source, engine_fingerprint_value, error_code, message)
            result = ProcessingResult(
                source=source,
                status="OCR_FAILED",
                error_code=error_code,
                error_message=message,
            )
            results.append(result)
        else:
            cache.store_success(source, engine_fingerprint_value, pages)
            result = ProcessingResult(source=source, status="OCR_SUCCEEDED", pages=pages)
            results.append(result)
        if on_progress:
            on_progress(current, total, result)
    return tuple(results)


def scan_inputs(order_dir: Path, bx_ids: set[str] | None = None, limit: int | None = None) -> ScanResult:
    return scan_order_files(order_dir, bx_ids=bx_ids, limit=limit)


def build_engine(
    models_dir: Path,
    manifest_path: Path,
    cpu_threads: int,
) -> PaddleOCREngine:
    return PaddleOCREngine.get_shared(models_dir, manifest_path, cpu_threads)


def fingerprint_without_loading_engine(manifest_path: Path) -> str:
    return engine_fingerprint(manifest_path)
