from datetime import datetime

from order_date.models import ExtractionResult
from order_date_rules_cli import materialize_source_result


def test_duplicate_materialization_keeps_prediction_and_uses_current_source():
    cached = ExtractionResult(
        "BX123",
        "first.jpg",
        "hash",
        "taobao",
        20,
        "ORDER-123",
        datetime(2026, 8, 16),
        90,
        "AUTO_ACCEPTED",
        "evidence",
        "rules-v1",
        1,
    )

    result = materialize_source_result(cached, "BX123", "second.jpg", duplicate=True)

    assert result.source_file == "second.jpg"
    assert result.order_datetime == cached.order_datetime
    assert result.status == "DUPLICATE"
    assert "内容哈希" in result.evidence_text
