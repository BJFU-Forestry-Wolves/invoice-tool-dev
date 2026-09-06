from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from order_date.cache_db import OCRCache
from order_date.input_loader import load_expense_records
from order_date.model_manager import default_models_dir
from order_date.pipeline import build_engine, fingerprint_without_loading_engine, process_sources, scan_inputs


PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_MANIFEST = PROJECT_ROOT / "models" / "manifest.json"


def configure_console_encoding() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except (AttributeError, OSError):
            pass
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass


def ensure_outside_repository(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved == PROJECT_ROOT or resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"{label}必须位于 Git 仓库外: {resolved}")
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="订单截图 OCR 与缓存主链路（P1）")
    parser.add_argument("--attach-root", required=True, type=Path, help="包含“订单截图”目录的附件根目录")
    parser.add_argument("--csv", type=Path, help="可选：只处理 CSV 中存在的 BX 编号")
    parser.add_argument("--bx", action="append", help="可重复指定要处理的 BX 编号")
    parser.add_argument("--cache", type=Path, help="SQLite 缓存；默认位于附件根目录的上级目录")
    parser.add_argument("--summary", type=Path, help="可选 JSON 运行摘要，必须位于 Git 仓库外")
    parser.add_argument("--models-dir", type=Path, default=default_models_dir())
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true", help="忽略已有 OCR 缓存")
    parser.add_argument("--scan-only", action="store_true", help="只扫描、校验和计算哈希，不运行 OCR")
    parser.add_argument("--quiet", action="store_true", help="不逐文件输出状态，只显示统计")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = parse_args(argv)
    attach_root = args.attach_root.resolve()
    order_dir = attach_root / "订单截图"
    bx_ids = {value.upper() for value in args.bx} if args.bx else None
    if args.csv:
        records = load_expense_records(args.csv.resolve())
        csv_bx_ids = {record.bx_id.upper() for record in records}
        bx_ids = csv_bx_ids if bx_ids is None else bx_ids & csv_bx_ids

    scan = scan_inputs(order_dir, bx_ids=bx_ids, limit=args.limit)
    print(f"扫描完成: 可处理={len(scan.files)}, 跳过={len(scan.issues)}")
    issue_counts = Counter(issue.code for issue in scan.issues)
    for code, count in sorted(issue_counts.items()):
        print(f"  {code}: {count}")
    if args.scan_only:
        return 0

    cache_path = ensure_outside_repository(
        args.cache or attach_root.parent / ".order_date_cache.sqlite3",
        "缓存文件",
    )
    summary_path = ensure_outside_repository(args.summary, "摘要文件") if args.summary else None
    fingerprint = fingerprint_without_loading_engine(MODEL_MANIFEST)
    engine = build_engine(args.models_dir, MODEL_MANIFEST, args.cpu_threads)
    with OCRCache(cache_path) as cache:
        results = process_sources(scan.files, cache, fingerprint, engine, force=args.force)

    status_counts = Counter(result.status for result in results)
    if not args.quiet:
        for result in results:
            page_count = len(result.pages)
            print(f"{result.status}: {result.source.relative_path} (pages={page_count})")
    print("处理统计: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())))

    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "scanned": len(scan.files),
                    "issues": dict(issue_counts),
                    "statuses": dict(status_counts),
                    "engine_fingerprint": fingerprint,
                    "files": [
                        {
                            "bx_id": result.source.bx_id,
                            "relative_path": result.source.relative_path,
                            "file_hash": result.source.file_hash,
                            "status": result.status,
                            "cached_status": result.cached_status,
                            "page_count": len(result.pages),
                            "error_code": result.error_code,
                        }
                        for result in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    cached_failures = sum(
        1 for result in results if result.status == "SKIPPED_CACHE" and result.cached_status == "OCR_FAILED"
    )
    return 1 if status_counts["OCR_FAILED"] or cached_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
