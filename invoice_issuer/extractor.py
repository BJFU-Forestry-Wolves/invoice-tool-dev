from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from order_date.models import OCRPage, OCRTextBlock

from .models import InvoiceIssuerResult


EXTRACTOR_VERSION = "2"
AUTO_ACCEPT_SCORE = 80.0
REVIEW_SCORE = 60.0
CONFLICT_DELTA = 8.0

SELLER_MARKERS = ("销售方信息", "销售方", "销货方", "销方信息", "销方", "卖方信息", "卖方")
BUYER_MARKERS = ("购买方信息", "购买方", "购方信息", "购方")
COMPANY_ENDINGS = (
    "有限责任公司",
    "股份有限公司",
    "集团有限公司",
    "有限公司",
    "公司",
    "个体工商户",
    "(个体工商户)",
    "专业合作社",
    "合作社",
    "研究院",
    "事务所",
    "经营部",
    "销售处",
    "服务部",
    "工作室",
    "商行",
    "商店",
    "门市部",
    "中心",
    "大学",
    "学院",
    "医院",
    "工厂",
    "厂",
    "店",
    "个人独资",
    "（个人独资）",
    "(个人独资)",
)
FIELD_TAIL_RE = re.compile(r"(?:统一社会信用代码|纳税人识别号|地址|电话|开户行|账号).*$")
NAME_PREFIX_RE = re.compile(r"^(?:(?:销售方|销方|卖方)(?:信息)?[：:]?)?(?:名称|名\s*称)[：:]?")


@dataclass(frozen=True, slots=True)
class _Candidate:
    name: str
    normalized: str
    score: float
    page_index: int
    evidence: tuple[str, ...]


def _bounds(block: OCRTextBlock) -> tuple[float, float, float, float]:
    xs = [point[0] for point in block.polygon]
    ys = [point[1] for point in block.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _center(block: OCRTextBlock) -> tuple[float, float]:
    x1, y1, x2, y2 = _bounds(block)
    return (x1 + x2) / 2, (y1 + y2) / 2


def _compact(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def _candidate_name(text: str) -> str | None:
    value = unicodedata.normalize("NFKC", text).strip()
    value = NAME_PREFIX_RE.sub("", value)
    value = FIELD_TAIL_RE.sub("", value)
    value = value.strip(" :：;；,，。|丨-—_[]【】")
    if not 4 <= len(value) <= 80:
        return None
    if sum("\u4e00" <= char <= "\u9fff" for char in value) < 2:
        return None
    if not value.endswith(COMPANY_ENDINGS):
        return None
    return value


def normalize_issuer_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).casefold()
    return "".join(char for char in value if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _near(marker: OCRTextBlock, block: OCRTextBlock) -> bool:
    mx, my = _center(marker)
    bx, by = _center(block)
    _, my1, _, my2 = _bounds(marker)
    height = max(1.0, my2 - my1)
    return bx >= mx - height * 2 and abs(by - my) <= height * 5


def _page_candidates(page: OCRPage) -> list[_Candidate]:
    blocks = page.blocks
    if not blocks:
        return []
    max_x = max(_bounds(block)[2] for block in blocks)
    min_x = min(_bounds(block)[0] for block in blocks)
    midpoint = (min_x + max_x) / 2
    seller_blocks = [block for block in blocks if any(marker in _compact(block.text) for marker in SELLER_MARKERS)]
    buyer_blocks = [block for block in blocks if any(marker in _compact(block.text) for marker in BUYER_MARKERS)]
    candidates: dict[str, _Candidate] = {}
    for block in blocks:
        name = _candidate_name(block.text)
        if name is None:
            continue
        normalized = normalize_issuer_name(name)
        compact = _compact(block.text)
        x, _ = _center(block)
        evidence: list[str] = []
        score = 30.0
        if "名称" in compact:
            score += 25
            evidence.append("名称标签 +25")
        seller_near = any(_near(marker, block) for marker in seller_blocks)
        buyer_near = any(_near(marker, block) for marker in buyer_blocks)
        if seller_near:
            score += 25
            evidence.append("销售方区域 +25")
        if x >= midpoint:
            score += 10
            evidence.append("页面右半区 +10")
        if buyer_near and not seller_near:
            score -= 30
            evidence.append("购买方区域 -30")
        if name.endswith(COMPANY_ENDINGS):
            score += 10
            evidence.append("机构名称后缀 +10")
        if block.confidence >= 0.85:
            score += 5
            evidence.append("OCR高置信 +5")
        candidate = _Candidate(name, normalized, max(0.0, min(100.0, score)), page.page_index, tuple(evidence))
        previous = candidates.get(normalized)
        if previous is None or candidate.score > previous.score:
            candidates[normalized] = candidate
    return list(candidates.values())


def extract_invoice_issuer(
    bx_id: str,
    source_file: str,
    file_hash: str,
    pages: tuple[OCRPage, ...],
) -> InvoiceIssuerResult:
    all_text = "".join(_compact(block.text) for page in pages for block in page.blocks)
    if "铁路电子客票" in all_text and ("12306" in all_text or "中国铁路" in all_text):
        name = "中国铁路（铁路电子客票）"
        return InvoiceIssuerResult(
            bx_id,
            source_file,
            file_hash,
            name,
            normalize_issuer_name(name),
            95.0,
            "AUTO_ACCEPTED",
            "识别到铁路电子客票和中国铁路/12306标识；票面未展示具体销售方法人名称，按铁路电子客票业务归组",
            1,
            page_index=0,
        )
    tax_invoice_markers = ("电子发票", "发票号码", "发票代码", "国家税务总局", "销售方信息", "销货方")
    supporting_document_markers = ("运单明细", "对账单", "费用明细", "申请开票日期")
    if any(marker in all_text for marker in supporting_document_markers) and not any(
        marker in all_text for marker in tax_invoice_markers
    ):
        return InvoiceIssuerResult(
            bx_id,
            source_file,
            file_hash,
            None,
            None,
            0.0,
            "NOT_INVOICE",
            "识别为运单/对账明细，且未发现税务发票版式标识，按非发票附件忽略",
            0,
            error_code="NOT_TAX_INVOICE",
        )
    candidates = sorted(
        (candidate for page in pages for candidate in _page_candidates(page)),
        key=lambda item: (-item.score, item.page_index, item.normalized),
    )
    if not candidates:
        if not any(marker in all_text for marker in tax_invoice_markers):
            return InvoiceIssuerResult(
                bx_id,
                source_file,
                file_hash,
                None,
                None,
                0.0,
                "NOT_INVOICE",
                "未发现税务发票版式标识，按非发票附件忽略",
                0,
                error_code="NOT_TAX_INVOICE",
            )
        return InvoiceIssuerResult(
            bx_id,
            source_file,
            file_hash,
            None,
            None,
            0.0,
            "NO_ISSUER",
            "未找到符合机构名称特征的销售方候选",
            0,
            error_code="ISSUER_NOT_FOUND",
        )
    best = candidates[0]
    conflicts = [item for item in candidates[1:] if best.score - item.score < CONFLICT_DELTA]
    if conflicts:
        status = "NEEDS_REVIEW"
    elif best.score >= AUTO_ACCEPT_SCORE:
        status = "AUTO_ACCEPTED"
    elif best.score >= REVIEW_SCORE:
        status = "NEEDS_REVIEW"
    else:
        status = "NO_ISSUER"
    evidence = "; ".join(best.evidence)
    if conflicts:
        evidence += f"; {len(conflicts)} 个近分公司候选"
    return InvoiceIssuerResult(
        bx_id,
        source_file,
        file_hash,
        best.name,
        best.normalized,
        best.score,
        status,
        evidence,
        len(candidates),
        page_index=best.page_index,
    )
