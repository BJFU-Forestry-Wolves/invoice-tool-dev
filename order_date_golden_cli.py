from __future__ import annotations

import argparse
from pathlib import Path

from order_date.golden_validator import DateValidationSummary, validate_golden_dates


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按年月日验证订单日期黄金样本")
    parser.add_argument("--predictions", required=True, type=Path, help="仓库外规则结果 JSON")
    parser.add_argument("--workbook", required=True, type=Path, help="仓库外人工标注工作簿")
    parser.add_argument("--minimum-auto-accuracy", type=float, default=0.99)
    return parser.parse_args(argv)


def _ratio(summary: DateValidationSummary, rows) -> str:
    correct = sum(row.correct for row in rows)
    return f"{correct}/{len(rows)} ({summary.accuracy(rows):.2%})"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = validate_golden_dates(args.predictions.resolve(), args.workbook.resolve())
    print(f"整体日期一致: {_ratio(summary, summary.rows)}")
    print(f"有日期样本: {_ratio(summary, summary.dated_rows)}")
    print(f"无日期样本: {_ratio(summary, summary.no_date_rows)}")
    print(f"自动通过样本: {_ratio(summary, summary.auto_accepted_rows)}")
    errors = [row for row in summary.rows if not row.correct]
    for row in errors:
        print(
            f"错误 行{row.row_number} {row.source_file}: "
            f"预测={row.predicted_date or '无日期'}, 人工={row.manual_date or '无日期'}, 状态={row.status}"
        )
    return 0 if summary.accuracy(summary.auto_accepted_rows) >= args.minimum_auto_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
