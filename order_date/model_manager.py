from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .ocr_engine import OCRModelError, validate_models


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "models" / "manifest.json"
DEFAULT_RELEASE_CONFIG = PROJECT_ROOT / "config" / "release.json"
MIRROR_ENV = "INVOICE_TOOL_MODEL_MIRROR"
ProgressCallback = Callable[[dict[str, object]], None]


class ModelDownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelStatus:
    ready: bool
    models_dir: Path
    message: str


def default_models_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "InvoiceAttachmentTool" / "models"
    return PROJECT_ROOT / ".paddlex-model-cache"


def inspect_models(
    models_dir: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> ModelStatus:
    target = (models_dir or default_models_dir()).resolve()
    try:
        validate_models(target, manifest_path)
    except (OCRModelError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        return ModelStatus(False, target, str(error))
    return ModelStatus(True, target, "OCR 模型已安装并通过哈希校验")


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ModelDownloadError(f"配置文件格式错误: {path}")
    return value


def _base_urls(config_path: Path, source: str) -> list[tuple[str, str]]:
    config = _read_json(config_path)
    repository = str(config.get("github_repository", "")).strip()
    release_tag = str(config.get("model_release_tag", "models-v1")).strip()
    mirror = os.environ.get(MIRROR_ENV, str(config.get("mirror_base_url", ""))).strip().rstrip("/")
    values: list[tuple[str, str]] = []
    if source in {"auto", "github"}:
        if not repository or "OWNER/REPOSITORY" in repository:
            if source == "github":
                raise ModelDownloadError("请先在 config/release.json 中填写 github_repository")
        else:
            values.append(("GitHub", f"https://github.com/{repository}/releases/download/{release_tag}"))
    if source in {"auto", "mirror"}:
        if not mirror:
            if source == "mirror":
                raise ModelDownloadError(
                    f"未配置镜像地址；请填写 mirror_base_url 或设置 {MIRROR_ENV}"
                )
        else:
            if not (mirror.startswith("https://") or mirror.startswith("file://")):
                raise ModelDownloadError("镜像地址必须使用 HTTPS；file:// 仅用于本地离线安装")
            values.append(("镜像", mirror))
    if not values:
        raise ModelDownloadError("没有可用的模型下载源，请检查 config/release.json")
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(
    url: str,
    destination: Path,
    expected_bytes: int,
    source_name: str,
    progress: ProgressCallback | None,
) -> None:
    existing = destination.stat().st_size if destination.exists() else 0
    headers = {"User-Agent": "InvoiceAttachmentTool/1.0"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        append = existing > 0 and getattr(response, "status", None) == 206
        if not append:
            existing = 0
        mode = "ab" if append else "wb"
        total_header = response.headers.get("Content-Length")
        response_bytes = int(total_header) if total_header and total_header.isdigit() else 0
        total = expected_bytes or (existing + response_bytes if response_bytes else 0)
        downloaded = existing
        with destination.open(mode) as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(
                        {
                            "stage": "model_download",
                            "source": source_name,
                            "current": downloaded,
                            "total": total,
                            "current_file": destination.name,
                        }
                    )


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            member = PurePosixPath(item.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ModelDownloadError(f"模型压缩包包含不安全路径: {item.filename}")
        bundle.extractall(destination)


def _install_staged(staged_root: Path, models_dir: Path) -> None:
    models_dir.parent.mkdir(parents=True, exist_ok=True)
    replacement = models_dir.parent / f".{models_dir.name}.new-{uuid.uuid4().hex}"
    backup = models_dir.parent / f".{models_dir.name}.backup-{uuid.uuid4().hex}"
    shutil.move(str(staged_root), str(replacement))
    old_exists = models_dir.exists()
    try:
        if old_exists:
            models_dir.rename(backup)
        replacement.rename(models_dir)
    except BaseException:
        if not models_dir.exists() and backup.exists():
            backup.rename(models_dir)
        raise
    finally:
        if replacement.exists():
            shutil.rmtree(replacement, ignore_errors=True)
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def download_and_install(
    *,
    source: str = "auto",
    models_dir: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    config_path: Path = DEFAULT_RELEASE_CONFIG,
    progress: ProgressCallback | None = None,
) -> ModelStatus:
    if source not in {"auto", "github", "mirror"}:
        raise ValueError(f"不支持的模型源: {source}")
    target = (models_dir or default_models_dir()).resolve()
    manifest = _read_json(manifest_path)
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        raise ModelDownloadError("模型清单缺少 bundle 配置")
    filename = str(bundle.get("filename", "")).strip()
    expected_hash = str(bundle.get("sha256", "")).strip().lower()
    archive_bytes = int(bundle.get("archive_bytes", 0) or 0)
    installed_bytes = int(bundle.get("installed_bytes", 0) or 0)
    if not filename or len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ModelDownloadError("模型包信息尚未完成，请先生成并更新 models/manifest.json")

    target.parent.mkdir(parents=True, exist_ok=True)
    required = archive_bytes + installed_bytes + 64 * 1024 * 1024
    if required and shutil.disk_usage(target.parent).free < required:
        raise ModelDownloadError("磁盘剩余空间不足，无法安全下载并安装模型")
    download_dir = target.parent / ".model-downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    partial = download_dir / f"{filename}.part"
    failures: list[str] = []
    for source_name, base_url in _base_urls(config_path, source):
        url = f"{base_url}/{filename}"
        try:
            _download(url, partial, archive_bytes, source_name, progress)
            actual_hash = _sha256(partial)
            if actual_hash != expected_hash:
                partial.unlink(missing_ok=True)
                raise ModelDownloadError(
                    f"模型包 SHA-256 不匹配（期望 {expected_hash}，实际 {actual_hash}）"
                )
            with tempfile.TemporaryDirectory(prefix="invoice-models-", dir=target.parent) as temp_name:
                extracted = Path(temp_name) / "models"
                extracted.mkdir()
                _safe_extract(partial, extracted)
                validate_models(extracted, manifest_path)
                _install_staged(extracted, target)
            partial.unlink(missing_ok=True)
            status = inspect_models(target, manifest_path)
            if progress:
                progress(
                    {
                        "stage": "model_done",
                        "source": source_name,
                        "current": 1,
                        "total": 1,
                        "current_file": filename,
                    }
                )
            return status
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ModelDownloadError) as error:
            failures.append(f"{source_name}: {error}")
    raise ModelDownloadError("所有模型下载源均失败：" + "；".join(failures))
