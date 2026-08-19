from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from order_date.workflow import WorkflowOptions, run_order_date_workflow
from order_date_cli import configure_console_encoding, default_models_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="订单日期 OCR、规则和 Excel 报告完整流程（P3）")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--attach-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--models-dir", type=Path, default=default_models_dir())
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--reimbursement-date", type=date.fromisoformat)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = parse_args(argv)

    def progress(event: dict[str, object]) -> None:
        stage = event.get("stage", "")
        current = event.get("current", 0)
        total = event.get("total", 0)
        current_file = event.get("current_file", "")
        print(f"[{stage}] {current}/{total} {current_file}")

    result = run_order_date_workflow(
        WorkflowOptions(
            csv_path=args.csv,
            attach_root=args.attach_root,
            output_dir=args.output_dir,
            cache_path=args.cache,
            models_dir=args.models_dir,
            cpu_threads=max(1, args.cpu_threads),
            force_reprocess=args.force_reprocess,
            reimbursement_date=args.reimbursement_date,
        ),
        progress,
    )
    print(f"Excel报告: {result.report_path}")
    print(f"规则结果: {result.result_json_path}")
    print(
        f"统计: 总文件={result.total_files}, 自动通过={result.accepted}, "
        f"待复核={result.review}, 失败={result.failed}"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
