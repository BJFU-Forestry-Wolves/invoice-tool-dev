from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_path
from .models import SourceFile


SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".pdf"})
BX_FILENAME_RE = re.compile(r"^(?P<bx>BX\d+)(?:\(\d+\))?\.[^.]+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ScanIssue:
    relative_path: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    files: tuple[SourceFile, ...]
    issues: tuple[ScanIssue, ...]


def extract_bx_id(filename: str) -> str | None:
    match = BX_FILENAME_RE.match(filename)
    return match.group("bx").upper() if match else None


def find_files_by_bx_id(directory: Path, bx_id: str) -> list[Path]:
    escaped = re.escape(bx_id)
    pattern = re.compile(rf"^{escaped}(?:\(\d+\))?\.[^.]+$", re.IGNORECASE)
    return sorted(
        (path for path in directory.glob(f"{bx_id}*") if path.is_file() and pattern.match(path.name)),
        key=lambda path: path.name.casefold(),
    )


def build_file_indexes(records, order_dir: Path, invoice_dir: Path):
    bx_ids = {record.bx_id if hasattr(record, "bx_id") else record["unique_id"] for record in records}
    return (
        {bx_id: find_files_by_bx_id(order_dir, bx_id) for bx_id in bx_ids},
        {bx_id: find_files_by_bx_id(invoice_dir, bx_id) for bx_id in bx_ids},
    )


def scan_order_files(order_dir: Path, bx_ids: set[str] | None = None, limit: int | None = None) -> ScanResult:
    root = order_dir.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"订单截图目录不存在: {root}")
    allowed_bx = {value.upper() for value in bx_ids} if bx_ids else None
    files: list[SourceFile] = []
    issues: list[ScanIssue] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        extension = path.suffix.lower()
        bx_id = extract_bx_id(path.name)
        if extension not in SUPPORTED_EXTENSIONS:
            issues.append(ScanIssue(relative, "UNSUPPORTED_EXTENSION", f"不支持的扩展名: {extension or '<none>'}"))
            continue
        if bx_id is None:
            issues.append(ScanIssue(relative, "INVALID_BX_FILENAME", "文件名不符合 BX编号[序号].扩展名"))
            continue
        if allowed_bx is not None and bx_id not in allowed_bx:
            continue
        stat = path.stat()
        files.append(
            SourceFile(
                bx_id=bx_id,
                path=path.resolve(),
                relative_path=relative,
                file_hash=sha256_path(path),
                extension=extension,
                file_size=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
        )
        if limit is not None and len(files) >= limit:
            break
    return ScanResult(tuple(files), tuple(issues))
