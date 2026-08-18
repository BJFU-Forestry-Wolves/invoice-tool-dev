import json
from pathlib import Path

from order_date.ocr_engine import PaddleOCREngine


class FakePipeline:
    def predict_iter(self, _path: str):
        yield {
            "rec_texts": [" ２０２６－０８－１６ "],
            "rec_scores": [0.98],
            "rec_polys": [[[0, 0], [10, 0], [10, 5], [0, 5]]],
        }


def test_engine_normalizes_incremental_pipeline_results(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"models": []}), encoding="utf-8")
    engine = PaddleOCREngine(tmp_path, manifest, 1, pipeline_factory=FakePipeline)

    pages = engine.predict(tmp_path / "anonymous.jpg")

    assert len(pages) == 1
    assert pages[0].blocks[0].normalized_text == "2026-08-16"
    assert pages[0].blocks[0].confidence == 0.98
