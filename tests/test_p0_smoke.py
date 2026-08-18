import json
from pathlib import Path

import p0_ocr_smoke


def test_smoke_manifest_has_ten_existing_multiformat_samples(tmp_path):
    sample_root = tmp_path / "anonymous-samples"
    sample_root.mkdir()
    suffixes = ["jpg", "jpg", "jpeg", "jpeg", "png", "png", "bmp", "bmp", "pdf", "pdf"]
    sample_names = []
    for index, suffix in enumerate(suffixes, start=1):
        name = f"sample-{index:02d}.{suffix}"
        (sample_root / name).write_bytes(b"test")
        sample_names.append(name)
    manifest_path = tmp_path / "smoke-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "sample_root": "anonymous-samples",
                "samples": [{"format": Path(name).suffix[1:], "path": name} for name in sample_names],
            }
        ),
        encoding="utf-8",
    )

    loaded_root, samples = p0_ocr_smoke.load_samples(manifest_path, None)

    assert loaded_root == sample_root
    assert len(samples) == 10
    assert {path.suffix.lower() for path in samples} == {".jpg", ".jpeg", ".png", ".bmp", ".pdf"}
    assert all(path.is_file() for path in samples)


def test_json_safe_converts_paths_and_nested_values():
    assert p0_ocr_smoke.json_safe({"path": Path("x"), "coords": (1, 2)}) == {
        "path": "x",
        "coords": [1, 2],
    }


def test_model_cache_avoids_non_ascii_project_path_on_windows():
    if p0_ocr_smoke.os.name == "nt" and p0_ocr_smoke.os.environ.get("LOCALAPPDATA"):
        assert p0_ocr_smoke.DEFAULT_MODELS.is_relative_to(Path(p0_ocr_smoke.os.environ["LOCALAPPDATA"]))


def test_compact_payload_drops_preprocessed_image():
    payload = p0_ocr_smoke.compact_ocr_payload(
        {"rec_texts": ["下单时间"], "doc_preprocessor_res": {"output_img": [[1, 2]]}}
    )

    assert payload == {"rec_texts": ["下单时间"]}


def test_compact_payload_unwraps_paddlex_result_envelope():
    payload = p0_ocr_smoke.compact_ocr_payload(
        {"res": {"rec_texts": ["下单时间"], "doc_preprocessor_res": {"output_img": [[1]]}}}
    )

    assert payload == {"rec_texts": ["下单时间"]}
