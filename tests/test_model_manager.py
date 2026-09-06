from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import zipfile
from pathlib import Path

import pytest

from order_date import model_manager


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_bundle(tmp_path: Path, *, unsafe: bool = False):
    payloads = {
        "orientation": ("ori", b"orientation-json", b"orientation-params"),
        "detection": ("det", b"detection-json", b"detection-params"),
        "recognition": ("rec", b"recognition-json", b"recognition-params"),
    }
    archive = tmp_path / "models.zip"
    with zipfile.ZipFile(archive, "w") as target:
        for name, inference, parameters in payloads.values():
            target.writestr(f"official_models/{name}/inference.json", inference)
            target.writestr(f"official_models/{name}/inference.pdiparams", parameters)
        if unsafe:
            target.writestr("../outside.txt", b"bad")
    manifest = {
        "schema_version": 2,
        "bundle": {
            "filename": archive.name,
            "archive_bytes": archive.stat().st_size,
            "installed_bytes": sum(len(item) for values in payloads.values() for item in values[1:]),
            "sha256": digest(archive.read_bytes()),
        },
        "models": [
            {
                "role": role,
                "name": name,
                "inference_json_sha256": digest(inference),
                "parameters_sha256": digest(parameters),
            }
            for role, (name, inference, parameters) in payloads.items()
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config_path = tmp_path / "release.json"
    config_path.write_text(
        json.dumps(
            {
                "github_repository": "example/repository",
                "model_release_tag": "models-v1",
                "mirror_base_url": "https://mirror.example/models-v1",
            }
        ),
        encoding="utf-8",
    )
    return archive, manifest_path, config_path


def test_status_reports_missing_models(tmp_path: Path):
    _, manifest, _ = build_bundle(tmp_path)
    status = model_manager.inspect_models(tmp_path / "missing", manifest)
    assert not status.ready


def test_download_installs_verified_bundle(tmp_path: Path, monkeypatch):
    archive, manifest, config = build_bundle(tmp_path)
    target = tmp_path / "installed"

    def fake_download(_url, destination, _expected, _source, _progress):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(model_manager, "_download", fake_download)
    status = model_manager.download_and_install(
        source="github", models_dir=target, manifest_path=manifest, config_path=config
    )
    assert status.ready
    assert (target / "official_models" / "rec" / "inference.pdiparams").is_file()


def test_auto_falls_back_to_mirror(tmp_path: Path, monkeypatch):
    archive, manifest, config = build_bundle(tmp_path)
    calls = []

    def fake_download(_url, destination, _expected, source, _progress):
        calls.append(source)
        if source == "GitHub":
            raise urllib.error.URLError("offline")
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(model_manager, "_download", fake_download)
    status = model_manager.download_and_install(
        source="auto", models_dir=tmp_path / "installed", manifest_path=manifest, config_path=config
    )
    assert status.ready
    assert calls == ["GitHub", "镜像"]


def test_hash_failure_preserves_existing_models(tmp_path: Path, monkeypatch):
    archive, manifest, config = build_bundle(tmp_path)
    target = tmp_path / "installed"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    def corrupt_download(_url, destination, _expected, _source, _progress):
        destination.write_bytes(archive.read_bytes() + b"corrupt")

    monkeypatch.setattr(model_manager, "_download", corrupt_download)
    with pytest.raises(model_manager.ModelDownloadError, match="所有模型下载源均失败"):
        model_manager.download_and_install(
            source="github", models_dir=target, manifest_path=manifest, config_path=config
        )
    assert marker.read_text(encoding="utf-8") == "keep"


def test_rejects_zip_path_traversal(tmp_path: Path):
    archive, _, _ = build_bundle(tmp_path, unsafe=True)
    with pytest.raises(model_manager.ModelDownloadError, match="不安全路径"):
        model_manager._safe_extract(archive, tmp_path / "extract")


def test_rejects_insecure_http_mirror(tmp_path: Path):
    _, _, config = build_bundle(tmp_path)
    config.write_text(
        json.dumps({"github_repository": "example/repository", "mirror_base_url": "http://example.test"}),
        encoding="utf-8",
    )
    with pytest.raises(model_manager.ModelDownloadError, match="HTTPS"):
        model_manager._base_urls(config, "mirror")
