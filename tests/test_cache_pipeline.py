from pathlib import Path

from order_date.cache_db import OCRCache
from order_date.models import OCRPage, OCRTextBlock, SourceFile
from order_date.pipeline import process_sources


def source_file(path: Path, file_hash: str = "abc") -> SourceFile:
    return SourceFile("BX123", path, path.name, file_hash, ".jpg", 5, 1)


class FakeEngine:
    def __init__(self, fingerprint: str = "engine-v1"):
        self.fingerprint = fingerprint
        self.calls = 0

    def predict(self, _path: Path):
        self.calls += 1
        block = OCRTextBlock("下单时间", "下单时间", 0.99, ((0, 0), (1, 0), (1, 1), (0, 1)), 0)
        return (OCRPage(0, (block,)),)


def test_pipeline_persists_result_and_skips_second_run(tmp_path: Path):
    path = tmp_path / "sample.jpg"
    path.write_bytes(b"image")
    source = source_file(path)
    engine = FakeEngine()
    with OCRCache(tmp_path / "cache.sqlite3") as cache:
        first = process_sources((source,), cache, engine.fingerprint, engine)
        second = process_sources((source,), cache, engine.fingerprint, engine)

    assert first[0].status == "OCR_SUCCEEDED"
    assert second[0].status == "SKIPPED_CACHE"
    assert second[0].cached_status == "OCR_SUCCEEDED"
    assert second[0].pages[0].blocks[0].normalized_text == "下单时间"
    assert engine.calls == 1


def test_engine_version_change_invalidates_ocr_layer(tmp_path: Path):
    path = tmp_path / "sample.jpg"
    path.write_bytes(b"image")
    source = source_file(path)
    first_engine = FakeEngine("engine-v1")
    second_engine = FakeEngine("engine-v2")
    with OCRCache(tmp_path / "cache.sqlite3") as cache:
        process_sources((source,), cache, first_engine.fingerprint, first_engine)
        result = process_sources((source,), cache, second_engine.fingerprint, second_engine)

    assert result[0].status == "OCR_SUCCEEDED"
    assert second_engine.calls == 1


def test_failure_is_cached_for_resume(tmp_path: Path):
    class BrokenEngine(FakeEngine):
        def predict(self, _path: Path):
            self.calls += 1
            raise RuntimeError("predict failed")

    path = tmp_path / "sample.jpg"
    path.write_bytes(b"image")
    source = source_file(path)
    engine = BrokenEngine()
    with OCRCache(tmp_path / "cache.sqlite3") as cache:
        first = process_sources((source,), cache, engine.fingerprint, engine)
        second = process_sources((source,), cache, engine.fingerprint, engine)

    assert first[0].status == "OCR_FAILED"
    assert second[0].status == "SKIPPED_CACHE"
    assert second[0].cached_status == "OCR_FAILED"
    assert engine.calls == 1
