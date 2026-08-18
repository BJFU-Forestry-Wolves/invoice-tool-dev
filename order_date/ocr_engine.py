from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .models import OCRPage
from .ocr_normalizer import normalize_page


OCR_ADAPTER_VERSION = "2"


class OCRModelError(RuntimeError):
    pass


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def engine_fingerprint(manifest_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(manifest_path.read_bytes())
    digest.update(f"\0ocr_adapter={OCR_ADAPTER_VERSION}".encode())
    for package in ("paddleocr", "paddlepaddle", "paddlex"):
        digest.update(f"\0{package}={_version(package)}".encode())
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_models(models_dir: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for model in manifest["models"]:
        direct_model_dir = models_dir / model["name"]
        official_model_dir = models_dir / "official_models" / model["name"]
        model_dir = direct_model_dir if direct_model_dir.is_dir() else official_model_dir
        checks = (
            (model_dir / "inference.json", model["inference_json_sha256"]),
            (model_dir / "inference.pdiparams", model["parameters_sha256"]),
        )
        for path, expected in checks:
            if not path.is_file():
                raise OCRModelError(f"模型文件缺失: {model['name']}/{path.name}")
            if _sha256(path) != expected:
                raise OCRModelError(f"模型文件哈希不匹配: {model['name']}/{path.name}")


def _payload(item: Any) -> dict[str, Any]:
    if hasattr(item, "json"):
        value = item.json() if callable(item.json) else item.json
    elif hasattr(item, "to_dict"):
        value = item.to_dict()
    else:
        value = item
    if not isinstance(value, dict):
        raise ValueError(f"不支持的 PaddleOCR 结果类型: {type(value).__name__}")
    if set(value) == {"res"} and isinstance(value["res"], dict):
        value = value["res"]
    return value


class PaddleOCREngine:
    _shared: "PaddleOCREngine | None" = None
    _shared_key: tuple[str, str, int] | None = None
    _lock = threading.Lock()

    def __init__(
        self,
        models_dir: Path,
        manifest_path: Path,
        cpu_threads: int,
        pipeline_factory: Callable[[], Any] | None = None,
    ):
        self.models_dir = models_dir.resolve()
        self.manifest_path = manifest_path.resolve()
        self.cpu_threads = cpu_threads
        self.fingerprint = engine_fingerprint(self.manifest_path)
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None

    @classmethod
    def get_shared(cls, models_dir: Path, manifest_path: Path, cpu_threads: int) -> "PaddleOCREngine":
        key = (str(models_dir.resolve()), str(manifest_path.resolve()), cpu_threads)
        with cls._lock:
            if cls._shared is None:
                cls._shared = cls(models_dir, manifest_path, cpu_threads)
                cls._shared_key = key
            elif cls._shared_key != key:
                raise RuntimeError("PaddleOCR 单例已使用不同配置初始化")
            return cls._shared

    def _create_pipeline(self):
        validate_models(self.models_dir, self.manifest_path)
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(self.models_dir)
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "1"
        from paddleocr import PaddleOCR

        return PaddleOCR(
            lang="ch",
            ocr_version="PP-OCRv6",
            device="cpu",
            engine="paddle_static",
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            cpu_threads=self.cpu_threads,
        )

    @property
    def pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._pipeline_factory() if self._pipeline_factory else self._create_pipeline()
        return self._pipeline

    def predict(self, path: Path) -> tuple[OCRPage, ...]:
        results: Iterable[Any] = self.pipeline.predict_iter(str(path))
        pages = []
        for page_index, item in enumerate(results):
            blocks = normalize_page(_payload(item), default_page_index=page_index)
            pages.append(OCRPage(page_index=page_index, blocks=blocks))
        return tuple(pages)
