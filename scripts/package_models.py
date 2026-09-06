from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from order_date.ocr_engine import validate_models


DEFAULT_MANIFEST = ROOT / "models" / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_models(models_dir: Path, output_dir: Path, manifest_path: Path, update_manifest: bool) -> Path:
    models_dir = models_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == ROOT or output_dir.is_relative_to(ROOT):
        raise ValueError("模型发布资源必须生成到 Git 仓库外")
    validate_models(models_dir, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = manifest["bundle"]
    archive = output_dir / bundle["filename"]
    output_dir.mkdir(parents=True, exist_ok=True)
    installed_bytes = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for model in manifest["models"]:
            direct = models_dir / model["name"]
            official = models_dir / "official_models" / model["name"]
            source_dir = direct if direct.is_dir() else official
            for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
                relative = source.relative_to(source_dir).as_posix()
                target.write(source, f"official_models/{model['name']}/{relative}")
                installed_bytes += source.stat().st_size
    archive_hash = _sha256(archive)
    (output_dir / f"{archive.name}.sha256").write_text(
        f"{archive_hash}  {archive.name}\n", encoding="ascii"
    )
    bundle.update(
        {
            "archive_bytes": archive.stat().st_size,
            "installed_bytes": installed_bytes,
            "sha256": archive_hash,
        }
    )
    generated_manifest = output_dir / "manifest.json"
    generated_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if update_manifest:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "UPLOAD.txt").write_text(
        "在 GitHub 仓库中创建标签为 models-v1 的 Release，并上传以下文件：\n"
        f"- {archive.name}\n- {archive.name}.sha256\n",
        encoding="utf-8",
    )
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成仓库外的 OCR 模型 Release 包")
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--update-manifest", action="store_true")
    args = parser.parse_args(argv)
    archive = package_models(args.models_dir, args.output_dir, args.manifest.resolve(), args.update_manifest)
    print(f"模型 Release 包: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
