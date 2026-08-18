import pytest

from order_date.ocr_normalizer import OCRNormalizationError, normalize_page, normalize_text


def test_normalize_text_applies_nfkc_and_trims():
    assert normalize_text(" ２０２６－０８－１６　") == "2026-08-16"


def test_normalize_page_preserves_original_text_and_geometry():
    blocks = normalize_page(
        {
            "page_index": None,
            "rec_texts": [" 下单时间 ", "　"],
            "rec_scores": [0.98, 0.2],
            "rec_polys": [
                [[1, 2], [11, 2], [11, 8], [1, 8]],
                [[0, 0], [1, 0], [1, 1], [0, 1]],
            ],
        }
    )

    assert len(blocks) == 1
    assert blocks[0].text == " 下单时间 "
    assert blocks[0].normalized_text == "下单时间"
    assert blocks[0].confidence == pytest.approx(0.98)
    assert blocks[0].polygon[0] == (1.0, 2.0)
    assert blocks[0].page_index == 0


def test_normalize_page_rejects_misaligned_fields():
    with pytest.raises(OCRNormalizationError, match="length mismatch"):
        normalize_page({"rec_texts": ["x"], "rec_scores": [], "rec_polys": []})

