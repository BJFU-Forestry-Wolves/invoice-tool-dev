import argparse
import csv
import re
import shutil
import string
import sys
from collections import Counter, defaultdict
from pathlib import Path

INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')
CIRCLE_BASE = 0x2460
DEFAULT_NAME_TEMPLATE = "{编号}_{上传人}_{用途}_{金额}_{附件标记}"
ALLOWED_TEMPLATE_FIELDS = {
    "编号",
    "上传人",
    "用途",
    "金额",
    "附件标记",
    "附件类型",
    "序号",
    "总数",
}

REQUIRED_COLUMNS = {
    "编号": "unique_id",
    "上传人": "uploader",
    "用途（必填）": "purpose",
    "税后金额": "amount",
    "发票": "invoice_filename",
    "订单截图": "order_filename",
}


def configure_console_encoding():
    """让打包后的程序在 Windows 终端中稳定输出中文。"""
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


def sanitize_filename(text: str) -> str:
    # 替换 Windows 非法文件名字符：\ / : * ? " < > |
    text = INVALID_FILENAME_RE.sub("_", text)
    # 移除或替换所有控制字符（换行、制表等），避免路径语法错误
    text = re.sub(r'[\x00-\x1f]', '', text)
    # 去除首尾空格和点号（Windows 不允许文件名以空格或点结尾）
    text = text.strip('. ')
    return text


def normalize_uploader(name: str) -> str:
    if name is None:
        return "未知上传者"
    if isinstance(name, str):
        normalized = name.replace("　", " ").strip()
        return " ".join(normalized.split()) or "未知上传者"
    return str(name).strip() or "未知上传者"


def circle_suffix(index: int) -> str:
    code_point = CIRCLE_BASE + index - 1
    if code_point <= 0x2473:
        return chr(code_point)
    return f"({index})"


def safe_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return sanitize_filename(text)


def validate_name_template(template: str) -> str:
    template = str(template).strip()
    if not template:
        raise ValueError("文件命名格式不能为空。")

    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        raise ValueError(f"文件命名格式中的大括号不完整: {error}") from error

    used_fields = set()
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in ALLOWED_TEMPLATE_FIELDS:
            raise ValueError(
                f"不支持的命名占位符: {{{field_name}}}。"
                f"可用占位符: {sorted(ALLOWED_TEMPLATE_FIELDS)}"
            )
        if format_spec or conversion:
            raise ValueError("命名占位符不支持格式说明符或转换标记。")
        used_fields.add(field_name)

    if not used_fields:
        raise ValueError("文件命名格式至少需要包含一个占位符。")
    return template


def render_target_filename(
    template: str,
    unique_id: str,
    uploader: str,
    purpose: str,
    amount: str,
    attachment_type: str,
    index: int,
    total: int,
    suffix: str,
) -> str:
    if attachment_type == "发票" and total == 1:
        attachment_mark = "发票"
    else:
        attachment_mark = f"{attachment_type}{index}(共{total})"

    values = {
        "编号": safe_text(unique_id),
        "上传人": safe_text(uploader),
        "用途": safe_text(purpose),
        "金额": safe_text(amount),
        "附件标记": attachment_mark,
        "附件类型": attachment_type,
        "序号": str(index),
        "总数": str(total),
    }
    filename_stem = sanitize_filename(template.format(**values))
    if not filename_stem:
        raise ValueError("文件命名格式生成了空文件名。")
    return f"{filename_stem}{suffix}"


def reserve_target_path(target_path: Path, generated_targets: set):
    normalized = str(target_path.resolve()).casefold()
    if normalized in generated_targets:
        raise ValueError(
            f"文件命名格式生成了重复目标，请增加“{{编号}}”或“{{附件标记}}”: {target_path.name}"
        )
    generated_targets.add(normalized)


def parse_csv(path: Path):
    """读取飞书导出的 UTF-8 BOM CSV，并转换成程序内部字段。"""
    records = []
    with path.open("r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        if reader.fieldnames is None:
            raise ValueError("CSV 中没有表头。")

        reader.fieldnames = [str(column).strip() for column in reader.fieldnames]
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV 缺少必需列: {sorted(missing)}")

        for row_number, row in enumerate(reader, start=2):
            normalized_row = {
                str(key).strip(): "" if value is None else str(value).strip()
                for key, value in row.items()
                if key is not None
            }
            record = {
                internal_name: normalized_row.get(column_name, "")
                for column_name, internal_name in REQUIRED_COLUMNS.items()
            }

            if not record["unique_id"]:
                print(f"[SKIP] 第 {row_number} 行编号为空。")
                continue

            if not any(record[field] for field in (
                "uploader", "purpose", "amount", "invoice_filename", "order_filename"
            )):
                print(f"[SKIP] 第 {row_number} 行除编号外均为空: {record['unique_id']}")
                continue

            record["uploader"] = normalize_uploader(record["uploader"])
            record["amount"] = record["amount"] or "未知金额"
            records.append(record)
    return records


def count_comma_segments(value: str) -> int:
    """统计逗号分隔的段数，用于判断发票/订单文件数量。"""
    if not value:
        return 0
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return len(parts)


def _find_files_by_unique_id(directory: Path, unique_id: str):
    """在目录中查找匹配 {unique_id}.ext 或 {unique_id}(N).ext 的所有文件（按文件名排序）。

    使用 glob 初步过滤后，再用正则确保精确匹配唯一编号，
    避免 BX123 误匹配 BX1234.pdf 这类前缀重叠。
    """
    escaped = re.escape(unique_id)
    exact_pattern = re.compile(rf"^{escaped}(?:\(\d+\))?\.[^.]+$", re.IGNORECASE)
    candidates = list(directory.glob(f"{unique_id}*"))
    files = [f for f in candidates if f.is_file() and exact_pattern.match(f.name)]
    return sorted(files, key=lambda p: p.name)


def build_file_index(records, order_dir: Path, invoice_dir: Path):
    order_index = defaultdict(list)
    invoice_index = defaultdict(list)
    unique_ids = {record["unique_id"] for record in records if record["unique_id"]}
    for unique_id in unique_ids:
        order_index[unique_id] = _find_files_by_unique_id(order_dir, unique_id)
        invoice_index[unique_id] = _find_files_by_unique_id(invoice_dir, unique_id)
    return order_index, invoice_index


def copy_file(src: Path, dst: Path, dry_run: bool):
    if dry_run:
        print(f"[DRY-RUN] Copy {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[COPY] Copy {src} -> {dst}")


def write_summary(summary_rows, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.csv"
    fieldnames = ["编号", "上传者", "用途", "税后金额", "发票重命名结果", "订单重命名结果", "缺失项"]
    try:
        with summary_path.open("w", encoding="utf-8-sig", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in summary_rows:
                writer.writerow(row)
        print(f"Summary written: {summary_path}")
    except PermissionError:
        # 如果文件被占用，尝试写入带时间戳的备用文件名
        import time
        alt_path = output_dir / f"summary_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        with alt_path.open("w", encoding="utf-8-sig", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in summary_rows:
                writer.writerow(row)
        print(f"Summary written (alternate): {alt_path}")
        print(f"注意: summary.csv 被其他程序占用，已写入备用文件。")


def main(argv=None):
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="批量重命名报销发票和订单截图文件")
    parser.add_argument("--csv", dest="csv_path", required=True, type=Path, help="报销数据 CSV 文件")
    parser.add_argument(
        "--attach-root",
        required=True,
        type=Path,
        help="附件根目录；其中必须包含“发票”和“订单截图”子目录",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="输出目录；默认在 CSV 所在目录生成“重命名结果”",
    )
    parser.add_argument(
        "--name-template",
        default=DEFAULT_NAME_TEMPLATE,
        help=f"文件名主体格式；扩展名自动保留。默认: {DEFAULT_NAME_TEMPLATE}",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印重命名计划，不执行复制")
    args = parser.parse_args(argv)

    csv_path = args.csv_path.resolve()
    attach_root = args.attach_root.resolve()
    invoice_dir = attach_root / "发票"
    order_dir = attach_root / "订单截图"
    output_dir = (args.output_dir or csv_path.parent / "重命名结果").resolve()
    try:
        name_template = validate_name_template(args.name_template)
    except ValueError as error:
        parser.error(str(error))

    if not csv_path.is_file():
        parser.error(f"CSV 文件不存在: {csv_path}")
    if not invoice_dir.is_dir():
        parser.error(f"发票目录不存在: {invoice_dir}")
    if not order_dir.is_dir():
        parser.error(f"订单截图目录不存在: {order_dir}")

    print(f"CSV path: {csv_path}")
    print(f"Invoice dir: {invoice_dir}")
    print(f"Order dir: {order_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Name template: {name_template}")
    if args.dry_run:
        print("Dry run enabled. 不会执行复制操作。\n")

    records = parse_csv(csv_path)
    if not records:
        print("CSV 中没有可处理的数据。")
        return

    grouped = defaultdict(list)
    for record in records:
        grouped[record["uploader"]].append(record)

    order_index, invoice_index = build_file_index(records, order_dir, invoice_dir)
    summary_rows = []
    generated_targets = set()
    abnormal_dir = output_dir / "异常订单"

    for uploader, group_records in grouped.items():
        print(f"\nProcessing uploader: {uploader} (rows: {len(group_records)})")
        purpose_counter = Counter()

        # 上传人目录名做安全处理，避免非法字符导致路径错误
        safe_uploader = safe_text(uploader)

        for record in group_records:
            unique_id = record["unique_id"].strip()
            purpose = record["purpose"].strip() or ""
            amount = record["amount"].strip() or "未知金额"
            invoice_name_raw = record["invoice_filename"].strip()
            order_name_raw = record["order_filename"].strip()

            if not unique_id:
                print("警告: 行中唯一编号为空，已跳过该行。")
                continue

            purpose_counter[purpose] += 1
            display_purpose = purpose
            if purpose and purpose_counter[purpose] > 1:
                display_purpose = f"{purpose}{circle_suffix(purpose_counter[purpose] - 1)}"

            invoice_result = "缺失"
            order_result = "缺失"
            missing_items = []

            # Invoice matching（与订单匹配逻辑对称：按逗号段数匹配多张发票）
            invoice_count = count_comma_segments(invoice_name_raw)
            if invoice_name_raw and invoice_count > 0:
                invoice_candidates = invoice_index.get(unique_id, [])
                assigned_inv = []
                for _ in range(min(invoice_count, len(invoice_candidates))):
                    assigned_inv.append(invoice_candidates.pop(0))
                if assigned_inv:
                    invoice_names = []
                    for index, src_file in enumerate(assigned_inv, 1):
                        target_invoice_name = render_target_filename(
                            name_template,
                            unique_id,
                            safe_uploader,
                            display_purpose,
                            amount,
                            "发票",
                            index,
                            invoice_count,
                            src_file.suffix,
                        )
                        target_invoice_path = output_dir / safe_uploader / target_invoice_name
                        reserve_target_path(target_invoice_path, generated_targets)
                        copy_file(src_file, target_invoice_path, args.dry_run)
                        invoice_names.append(target_invoice_name)
                    invoice_result = "; ".join(invoice_names)
                    if len(assigned_inv) < invoice_count:
                        missing_items.append(f"发票缺失{invoice_count - len(assigned_inv)}个")
                        print(f"[PARTIAL] 发票文件不足: {unique_id} 需要 {invoice_count} 个，找到 {len(assigned_inv)} 个")
                else:
                    missing_items.append("发票缺失")
                    print(f"[MISSING] 发票未找到: {unique_id} ({uploader})")
            else:
                missing_items.append("发票缺失")
                if invoice_name_raw:
                    print(f"[WARNING] 发票列内容无效，视为缺失: {unique_id} ({uploader})")
                else:
                    print(f"[MISSING] 发票列为空: {unique_id} ({uploader})")

            # Order matching
            order_count = count_comma_segments(order_name_raw)
            if order_name_raw and order_count > 0:
                order_candidates = order_index.get(unique_id, [])
                assigned = []
                for _ in range(min(order_count, len(order_candidates))):
                    assigned.append(order_candidates.pop(0))
                if assigned:
                    order_names = []
                    for index, src_file in enumerate(assigned, 1):
                        target_order_name = render_target_filename(
                            name_template,
                            unique_id,
                            safe_uploader,
                            display_purpose,
                            amount,
                            "订单",
                            index,
                            order_count,
                            src_file.suffix,
                        )
                        target_order_path = output_dir / safe_uploader / target_order_name
                        reserve_target_path(target_order_path, generated_targets)
                        copy_file(src_file, target_order_path, args.dry_run)
                        order_names.append(target_order_name)
                    order_result = "; ".join(order_names)
                    if len(assigned) < order_count:
                        missing_items.append(f"订单缺失{order_count - len(assigned)}个")
                        print(f"[PARTIAL] 订单文件不足: {unique_id} 需要 {order_count} 个，找到 {len(assigned)} 个")
                else:
                    missing_items.append("订单缺失")
                    print(f"[MISSING] 订单未找到: {unique_id} ({uploader})")
            else:
                missing_items.append("订单缺失")
                if order_name_raw:
                    print(f"[WARNING] 订单截图列内容无效，视为缺失: {unique_id} ({uploader})")
                else:
                    print(f"[MISSING] 订单截图列为空: {unique_id} ({uploader})")

            summary_rows.append({
                "编号": unique_id,
                "上传者": uploader,
                "用途": display_purpose,
                "税后金额": amount,
                "发票重命名结果": invoice_result,
                "订单重命名结果": order_result,
                "缺失项": "; ".join(missing_items),
            })

    # 所有记录处理完毕后，再统一复制未匹配附件，避免重复编号造成重复处理。
    for leftover_files in order_index.values():
        for leftover in leftover_files:
            target_path = abnormal_dir / leftover.name
            copy_file(leftover, target_path, args.dry_run)
            print(f"[UNMATCHED] 剩余订单文件复制到异常订单: {leftover.name}")

    for leftover_files in invoice_index.values():
        for leftover in leftover_files:
            target_path = abnormal_dir / leftover.name
            copy_file(leftover, target_path, args.dry_run)
            print(f"[UNMATCHED] 剩余发票文件复制到异常订单: {leftover.name}")

    if not args.dry_run:
        write_summary(summary_rows, output_dir)
    else:
        print("\nDry run 模式，不写入 summary.csv")


if __name__ == "__main__":
    main()
