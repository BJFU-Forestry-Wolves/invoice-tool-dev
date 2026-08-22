from datetime import date
from decimal import Decimal

from invoice_issuer.aggregator import aggregate_daily_merchants
from invoice_issuer.extractor import extract_invoice_issuer, normalize_issuer_name
from invoice_issuer.models import InvoiceContext, InvoiceIssuerResult
from order_date.models import OCRPage, OCRTextBlock


def block(text: str, x: float, y: float, confidence: float = 0.99) -> OCRTextBlock:
    return OCRTextBlock(text, text, confidence, ((x, y), (x + 160, y), (x + 160, y + 20), (x, y + 20)), 0)


def test_extracts_seller_name_instead_of_buyer_name():
    page = OCRPage(
        0,
        (
            block("购买方信息", 0, 40),
            block("名称：北京林业大学", 60, 40),
            block("销售方信息", 500, 40),
            block("名称：辽宁全景智能科技有限公司", 560, 40),
        ),
    )

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.issuer_name == "辽宁全景智能科技有限公司"
    assert result.status == "AUTO_ACCEPTED"


def test_normalizes_company_spacing_and_parentheses():
    assert normalize_issuer_name("苏州 优逸思（电子）科技有限公司") == "苏州优逸思电子科技有限公司"


def test_groups_railway_e_ticket_without_inventing_legal_company():
    page = OCRPage(
        0,
        (
            block("电子发票（铁路电子客票）", 0, 0),
            block("买票请到12306", 0, 40),
            block("中国铁路祝您旅途愉快", 0, 80),
        ),
    )

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.issuer_name == "中国铁路（铁路电子客票）"
    assert result.status == "AUTO_ACCEPTED"
    assert "未展示具体销售方法人名称" in result.evidence_text


def test_accepts_sales_office_and_seller_legacy_label():
    page = OCRPage(
        0,
        (
            block("购买方", 0, 40),
            block("名称：北京林业大学", 30, 70),
            block("销货方", 500, 40),
            block("名称：临西县志兴轴承销售处", 530, 70),
        ),
    )

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.issuer_name == "临西县志兴轴承销售处"
    assert result.status == "AUTO_ACCEPTED"


def test_accepts_sole_proprietorship_legal_form():
    page = OCRPage(
        0,
        (
            block("购买方信息", 0, 40),
            block("名称：北京林业大学", 30, 70),
            block("销售方信息", 500, 40),
            block("名称：襄阳市襄州区经济销售铺（个人独资）", 530, 70),
        ),
    )

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.issuer_name == "襄阳市襄州区经济销售铺(个人独资)"
    assert result.status == "AUTO_ACCEPTED"


def test_preserves_parenthesized_individual_business_legal_form():
    page = OCRPage(
        0,
        (
            block("销售方信息", 500, 40),
            block("名称：示例商行（个体工商户）", 530, 70),
        ),
    )

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.issuer_name == "示例商行(个体工商户)"
    assert result.status == "AUTO_ACCEPTED"


def test_marks_supporting_document_as_not_invoice():
    page = OCRPage(0, (block("京东快递——运单明细", 0, 0), block("公司名称 北京林业大学", 0, 40)))

    result = extract_invoice_issuer("BX1", "BX1.pdf", "hash", (page,))

    assert result.status == "NOT_INVOICE"


def issuer_result(bx_id: str, source: str, issuer: str, status: str = "AUTO_ACCEPTED") -> InvoiceIssuerResult:
    return InvoiceIssuerResult(
        bx_id,
        source,
        source,
        issuer,
        normalize_issuer_name(issuer),
        90,
        status,
        "销售方区域",
        1,
        0,
    )


def context(bx_id: str, source: str, amount: str, day: date | None) -> InvoiceContext:
    return InvoiceContext(bx_id, source, day, Decimal(amount), "上传人", "用途")


def test_aggregates_once_per_bx_date_and_flags_over_1000():
    day = date(2026, 4, 16)
    results = (
        issuer_result("BX1", "BX1.pdf", "示例科技有限公司"),
        issuer_result("BX2", "BX2.pdf", "示例科技有限公司"),
    )
    contexts = {
        "bx1.pdf": (context("BX1", "BX1.pdf", "600", day),),
        "bx2.pdf": (context("BX2", "BX2.pdf", "450", day),),
    }

    groups, review = aggregate_daily_merchants(results, contexts)

    assert not review
    assert len(groups) == 1
    assert groups[0].total_amount == Decimal("1050")
    assert groups[0].status == "EXCEEDED"


def test_does_not_double_count_multiple_same_issuer_invoices_for_one_bx():
    day = date(2026, 4, 16)
    results = (
        issuer_result("BX1", "BX1.pdf", "示例科技有限公司"),
        issuer_result("BX1", "BX1(1).pdf", "示例科技有限公司"),
    )
    contexts = {
        "bx1.pdf": (context("BX1", "BX1.pdf", "700", day),),
        "bx1(1).pdf": (context("BX1", "BX1(1).pdf", "700", day),),
    }

    groups, review = aggregate_daily_merchants(results, contexts)

    assert not review
    assert groups[0].total_amount == Decimal("700")


def test_multiple_issuers_for_one_record_requires_review():
    day = date(2026, 4, 16)
    results = (
        issuer_result("BX1", "BX1.pdf", "甲公司"),
        issuer_result("BX1", "BX1(1).pdf", "乙公司"),
    )
    contexts = {
        "bx1.pdf": (context("BX1", "BX1.pdf", "900", day),),
        "bx1(1).pdf": (context("BX1", "BX1(1).pdf", "900", day),),
    }

    groups, review = aggregate_daily_merchants(results, contexts)

    assert not groups
    assert review[0].reason == "同一报销编号识别到多个开票公司，无法分配记录金额"


def test_merges_missing_date_review_rows_for_same_bx():
    results = (
        issuer_result("BX1", "BX1.pdf", "示例科技有限公司"),
        issuer_result("BX1", "BX1(1).pdf", "示例科技有限公司"),
    )
    contexts = {
        "bx1.pdf": (context("BX1", "BX1.pdf", "1500", None),),
        "bx1(1).pdf": (context("BX1", "BX1(1).pdf", "1500", None),),
    }

    groups, review = aggregate_daily_merchants(results, contexts)

    assert not groups
    assert len(review) == 1
    assert review[0].source_files == ("BX1(1).pdf", "BX1.pdf")
