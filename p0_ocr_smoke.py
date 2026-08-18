from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "p0-results"


def default_models_dir() -> Path:
    # Paddle Inference 3.2.0 cannot open static model files through a Windows
    # path containing non-ASCII characters. Use a stable per-user ASCII path;
    # release builds will copy verified bundled models here before loading.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "InvoiceAttachmentTool" / "models"
    return PROJECT_ROOT / ".paddlex-model-cache"


DEFAULT_MODELS = default_models_dir()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass
    if hasattr(value, "json"):
        try:
            payload = value.json
            return json_safe(payload() if callable(payload) else payload)
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return json_safe(value.to_dict())
        except Exception:
            pass
    return repr(value)


def result_items(result: Any) -> Iterable[Any]:
    if isinstance(result, (str, bytes, dict)):
        yield result
        return
    try:
        yield from result
    except TypeError:
        yield result


OCR_RESULT_FIELDS = (
    "input_path",
    "page_index",
    "dt_polys",
    "model_settings",
    "text_det_params",
    "text_type",
    "text_rec_score_thresh",
    "return_word_box",
    "rec_texts",
    "rec_scores",
    "rec_polys",
    "textline_orientation_angles",
    "rec_boxes",
)


def compact_ocr_payload(value: Any) -> Any:
    if hasattr(value, "json"):
        payload = value.json() if callable(value.json) else value.json
    elif hasattr(value, "to_dict"):
        payload = value.to_dict()
    else:
        payload = value
    if isinstance(payload, dict) and set(payload) == {"res"} and isinstance(payload["res"], dict):
        payload = payload["res"]
    if isinstance(payload, dict):
        payload = {key: payload[key] for key in OCR_RESULT_FIELDS if key in payload}
    return json_safe(payload)


def load_samples(manifest_path: Path, limit: int | None) -> tuple[Path, list[Path]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    configured_root = manifest.get("sample_root")
    if configured_root:
        sample_root = (manifest_path.parent / configured_root).resolve()
    else:
        sample_root = manifest_path.parent.resolve()
    paths = [(sample_root / item["path"]).resolve() for item in manifest["samples"]]
    if limit is not None:
        paths = paths[:limit]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing smoke samples:\n" + "\n".join(missing))
    return sample_root, paths


def create_pipeline(models_dir: Path, cpu_threads: int):
    # PaddleX reads its cache location during import. Keep downloaded models in
    # the project so they can be hashed and shipped for offline use.
    models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(models_dir)
    from paddleocr import PaddleOCR

    kwargs: dict[str, Any] = {
        "lang": "ch",
        "ocr_version": "PP-OCRv6",
        "device": "cpu",
        "engine": "paddle_static",
        "use_doc_orientation_classify": True,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "cpu_threads": cpu_threads,
    }
    return PaddleOCR(**kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0 PaddleOCR compatibility smoke test")
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a local manifest stored outside the Git repository",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--cpu-threads", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--check-only", action="store_true", help="Validate inputs and versions without loading OCR")
    return parser.parse_args()


def main() -> int:
    import psutil

    run_started = time.perf_counter()
    process = psutil.Process()
    args = parse_args()
    sample_root, samples = load_samples(args.manifest.resolve(), args.limit)
    metadata = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            name: package_version(name)
            for name in ("paddleocr", "paddlepaddle", "paddlex", "Pillow", "psutil")
        },
        "samples": [
            {"path": str(path.relative_to(sample_root)), "size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in samples
        ],
    }
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if args.check_only:
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pipeline_started = time.perf_counter()
    pipeline = create_pipeline(args.models_dir.resolve(), args.cpu_threads)
    metadata["pipeline_init_seconds"] = round(time.perf_counter() - pipeline_started, 3)

    failures = 0
    for path in samples:
        started = time.perf_counter()
        record: dict[str, Any] = {
            "source": str(path.relative_to(sample_root)),
            "sha256": sha256_file(path),
        }
        try:
            record["results"] = [compact_ocr_payload(item) for item in result_items(pipeline.predict_iter(str(path)))]
            record["status"] = "ok"
        except Exception as exc:
            failures += 1
            record.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        output_path = args.output_dir / f"{path.name}.ocr.json"
        output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{record['status']}: {path.name} ({record['elapsed_seconds']}s)")

    metadata["failure_count"] = failures
    memory = process.memory_info()
    metadata["total_seconds"] = round(time.perf_counter() - run_started, 3)
    metadata["peak_working_set_bytes"] = getattr(memory, "peak_wset", memory.rss)
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
