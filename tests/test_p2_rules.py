from datetime import datetime
from pathlib import Path

from order_date.aggregator import aggregate_bx_results
from order_date.candidate_extractor import extract_date_candidates
from order_date.extractor import extract_order_date
from order_date.models import ExtractionResult, OCRPage, OCRTextBlock
from order_date.platform_detector import detect_platform
from order_date.rules_loader import load_rules


RULES = load_rules(Path(__file__).parents[1] / "order_date" / "rules")


def block(text: str, x: float, y: float, confidence: float = 0.99) -> OCRTextBlock:
    return OCRTextBlock(text, text, confidence, ((x, y), (x + 80, y), (x + 80, y + 20), (x, y + 20)), 0)


def test_platform_detection_and_strong_date_scoring():
    page = OCRPage(0, (block("京东订单", 0, 0), block("下单时间", 0, 40), block("2026-08-16 12:34:56", 100, 40)))

    platform = detect_platform((page,), RULES)
    result = extract_order_date("BX123", "sample.jpg", "hash", (page,), RULES)

    assert platform.platform == "jd"
    assert result.order_datetime == datetime(2026, 8, 16, 12, 34, 56)
    assert result.status == "AUTO_ACCEPTED"
    assert result.confidence_score >= 85


def test_platform_detection_does_not_affect_date_acceptance():
    known_page = OCRPage(
        0,
        (block("京东订单", 0, 0), block("下单时间", 0, 40), block("2026-08-16 12:34:56", 100, 40)),
    )
    unknown_page = OCRPage(
        0,
        (block("订单详情", 0, 0), block("下单时间", 0, 40), block("2026-08-16 12:34:56", 100, 40)),
    )

    known = extract_order_date("BX123", "known.jpg", "known", (known_page,), RULES)
    unknown = extract_order_date("BX124", "unknown.jpg", "unknown", (unknown_page,), RULES)

    assert known.platform == "jd"
    assert unknown.platform == "unknown"
    assert known.confidence_score == unknown.confidence_score
    assert known.status == unknown.status == "AUTO_ACCEPTED"


def test_date_extractor_rejects_invalid_calendar_date_and_supports_chinese():
    page = OCRPage(0, (block("2026年2月30日", 0, 0), block("2026年2月28日 08:01", 0, 30)))

    candidates = extract_date_candidates((page,))

    assert {candidate.normalized_datetime for candidate in candidates} == {datetime(2026, 2, 28, 8, 1)}


def test_payment_date_is_not_auto_accepted():
    page = OCRPage(
        0,
        (
            block("淘宝", 0, 0),
            block("付款时间", 0, 40),
            block("2026-08-16 12:34:56", 100, 40),
            block("发货时间", 0, 80),
            block("2026-08-17 12:34:56", 100, 80),
        ),
    )

    result = extract_order_date("BX123", "sample.jpg", "hash", (page,), RULES)

    assert result.status == "NO_ORDER_DATE"
    assert "排除标签" in result.evidence_text


def test_adjacent_payment_and_delivery_rows_do_not_override_order_date():
    page = OCRPage(
        0,
        (
            block("京东订单", 0, 0),
            block("支付时间", 0, 40),
            block("2026-04-08 22:32:05", 100, 40),
            block("下单时间", 0, 80),
            block("2026-04-08 22:31:57", 100, 80),
            block("期望配送时间", 0, 120),
            block("2026-04-09 09:00", 100, 120),
        ),
    )

    result = extract_order_date("BX123", "sample.jpg", "hash", (page,), RULES)

    assert result.order_datetime == datetime(2026, 4, 8, 22, 31, 57)
    assert result.status == "AUTO_ACCEPTED"


def test_creation_time_row_is_not_penalized_by_excluded_labels_above():
    page = OCRPage(
        0,
        (
            block("天猫", 0, 0),
            block("成交时间", 0, 40),
            block("2026-03-29 10:14:21", 100, 40),
            block("发货时间", 0, 80),
            block("2026-03-19 10:14:11", 100, 80),
            block("付款时间", 0, 120),
            block("2026-03-19 08:29:37", 100, 120),
            block("创建时间", 0, 160),
            block("2026-03-19 08:29:25", 100, 160),
        ),
    )

    result = extract_order_date("BX123", "sample.jpg", "hash", (page,), RULES)

    assert result.order_datetime == datetime(2026, 3, 19, 8, 29, 25)
    assert result.status == "AUTO_ACCEPTED"
    assert "排除标签" not in result.evidence_text


def extraction(source: str, order: str | None, moment: datetime, score: float = 80) -> ExtractionResult:
    return ExtractionResult(
        "BX123", source, source, "jd", 20, order, moment, score, "NEEDS_REVIEW", "evidence", RULES.version, 1
    )


def test_aggregator_boosts_matching_attachments_and_flags_conflict():
    moment = datetime(2026, 8, 16, 12, 0)
    matching = aggregate_bx_results(
        (extraction("a", "ORDER-123", moment), extraction("b", "ORDER-123", moment)), RULES
    )
    conflict = aggregate_bx_results(
        (extraction("a", "ORDER-123", moment), extraction("b", "ORDER-123", datetime(2026, 8, 17, 12, 0))), RULES
    )

    assert matching[0].confidence_score == 90
    assert matching[0].status == "AUTO_ACCEPTED"
    assert conflict[0].status == "CONFLICT"


def test_aggregator_treats_different_times_on_same_date_as_matching():
    matching = aggregate_bx_results(
        (
            extraction("a", "ORDER-123", datetime(2026, 8, 16, 8, 0)),
            extraction("b", "ORDER-123", datetime(2026, 8, 16, 20, 0)),
        ),
        RULES,
    )

    assert len(matching) == 1
    assert matching[0].status == "AUTO_ACCEPTED"
    assert matching[0].order_datetime.date() == datetime(2026, 8, 16).date()
