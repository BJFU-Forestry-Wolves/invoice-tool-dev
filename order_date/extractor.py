from __future__ import annotations

from datetime import date

from .candidate_extractor import extract_date_candidates, extract_order_number
from .models import ExtractionResult, OCRPage
from .platform_detector import detect_platform
from .rule_scorer import score_candidates, status_for_score
from .rules_loader import RuleSet


def extract_order_date(
    bx_id: str,
    source_file: str,
    file_hash: str,
    pages: tuple[OCRPage, ...],
    rules: RuleSet,
    reimbursement_date: date | None = None,
) -> ExtractionResult:
    platform = detect_platform(pages, rules)
    platform_rule = next((rule for rule in rules.platforms if rule.platform == platform.platform), None)
    order_number = extract_order_number(pages, platform_rule, rules)
    candidates = extract_date_candidates(pages)
    scored = score_candidates(pages, candidates, platform, platform_rule, rules)
    if not scored:
        return ExtractionResult(
            bx_id,
            source_file,
            file_hash,
            platform.platform,
            platform.score,
            order_number,
            None,
            0.0,
            "NO_ORDER_DATE",
            "未提取到完整年份日期候选",
            rules.version,
            0,
        )

    best = scored[0]
    status = status_for_score(best.score, rules)
    thresholds = rules.common["thresholds"]
    threshold = thresholds["candidate_conflict_delta"]
    competing = [
        item
        for item in scored[1:]
        if item.candidate.normalized_datetime != best.candidate.normalized_datetime
        and best.score >= thresholds["needs_review"]
        and item.score >= thresholds["needs_review"]
        and best.score - item.score < threshold
    ]
    if competing:
        status = "CONFLICT"
    if reimbursement_date and best.candidate.normalized_datetime.date() > reimbursement_date:
        status = "NEEDS_REVIEW"
    evidence = "; ".join(best.reasons)
    if competing:
        evidence += f"; {len(competing)} 个近分候选冲突"
    if reimbursement_date and best.candidate.normalized_datetime.date() > reimbursement_date:
        evidence += "; 日期晚于报销日期"
    return ExtractionResult(
        bx_id=bx_id,
        source_file=source_file,
        file_hash=file_hash,
        platform=platform.platform,
        platform_score=platform.score,
        order_number=order_number,
        order_datetime=best.candidate.normalized_datetime,
        confidence_score=best.score,
        status=status,
        evidence_text=evidence,
        rule_version=rules.version,
        candidate_count=len(scored),
        page_index=best.candidate.page_index,
    )
