from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from order_date.full_validator import build_validation_metrics, write_validation_csv
from order_date.workflow import WorkflowOptions, run_order_date_workflow
from order_date_cli import configure_console_encoding, default_models_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="订单日期 P4 全量验证")
    parser.add_argument("--scan-summary", required=True, type=Path)
    parser.add_argument("--golden-workbook", required=True, type=Path)
    parser.add_argument("--attach-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--models-dir", type=Path, default=default_models_dir())
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--minimum-auto-accuracy", type=float, default=0.99)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = parse_args(argv)
    output_dir = args.output_dir.resolve()
    validation_csv = output_dir / "p4-full-validation-input.csv"
    bx_count = write_validation_csv(args.scan_summary.resolve(), validation_csv)
    print(f"验证清单: {bx_count} 个 BX 编号")

    def progress(event: dict[str, object]) -> None:
        print(
            f"[{event.get('stage', '')}] {event.get('current', 0)}/{event.get('total', 0)} "
            f"{event.get('current_file', '')}"
        )

    started = perf_counter()
    result = run_order_date_workflow(
        WorkflowOptions(
            csv_path=validation_csv,
            attach_root=args.attach_root.resolve(),
            output_dir=output_dir,
            cache_path=args.cache.resolve(),
            models_dir=args.models_dir,
            cpu_threads=max(1, args.cpu_threads),
            force_reprocess=args.force_reprocess,
        ),
        progress,
    )
    metrics = build_validation_metrics(
        result.result_json_path,
        args.golden_workbook.resolve(),
        perf_counter() - started,
    )
    metrics_path = output_dir / "P4全量验证指标.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    golden = metrics["golden"]
    print(f"Excel报告: {result.report_path}")
    print(f"验证指标: {metrics_path}")
    print(f"整体日期一致: {golden['overall']['correct']}/{golden['overall']['total']} ({golden['overall']['accuracy']:.2%})")
    print(
        f"自动通过日期一致: {golden['auto_accepted']['correct']}/{golden['auto_accepted']['total']} "
        f"({golden['auto_accepted']['accuracy']:.2%})"
    )
    return 0 if golden["auto_accepted"]["accuracy"] >= args.minimum_auto_accuracy and result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
