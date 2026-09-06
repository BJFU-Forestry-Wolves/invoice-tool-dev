from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from invoice_issuer.workflow import WorkflowOptions, run_invoice_issuer_workflow


PROJECT_ROOT = Path(__file__).resolve().parent


def _default_models_dir() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) / "InvoiceAttachmentTool" / "models" if value else PROJECT_ROOT / ".paddlex-model-cache"


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识别发票销售方，并按指定限额检查单日同公司合计")
    parser.add_argument("--manifest", required=True, type=Path, help="分类流程生成的 classification_manifest.json")
    parser.add_argument("--attach-root", required=True, type=Path, help="包含“发票”目录的附件根目录")
    parser.add_argument("--output-dir", required=True, type=Path, help="结果目录，必须位于 Git 仓库外")
    parser.add_argument("--cache", type=Path, help="OCR SQLite 缓存，必须位于 Git 仓库外")
    parser.add_argument("--models-dir", type=Path, default=_default_models_dir())
    parser.add_argument("--cpu-threads", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--limit", type=int, help="仅处理前 N 份发票，用于抽样测试")
    parser.add_argument("--force", action="store_true", help="忽略 OCR 缓存重新识别")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--daily-limit", default="1000", help="单日同开票公司限额，默认 1000")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = parse_args(argv)
    try:
        daily_limit = Decimal(args.daily_limit)
        if daily_limit <= 0:
            raise InvalidOperation
    except InvalidOperation as error:
        raise SystemExit("--daily-limit 必须是大于 0 的金额") from error

    def progress(event: dict[str, object]) -> None:
        if args.quiet:
            return
        stage = event.get("stage")
        if stage in {"ocr", "extract"}:
            print(f"[{stage}] {event.get('current')}/{event.get('total')} {event.get('current_file')}")

    result = run_invoice_issuer_workflow(
        WorkflowOptions(
            manifest_path=args.manifest,
            attach_root=args.attach_root,
            output_dir=args.output_dir,
            cache_path=args.cache,
            models_dir=args.models_dir,
            cpu_threads=args.cpu_threads,
            force_reprocess=args.force,
            limit=args.limit,
            daily_limit=daily_limit,
        ),
        progress,
    )
    print(f"结果: {result.result_json_path}")
    print(f"Excel报告: {result.report_path}")
    print(
        f"统计: 发票={result.total_files}, 自动通过={result.accepted}, 待复核={result.review}, "
        f"OCR失败={result.failed}, 日公司组={result.daily_groups}, 超额组={result.exceeded_groups}"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
