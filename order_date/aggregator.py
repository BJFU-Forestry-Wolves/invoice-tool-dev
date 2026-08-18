from __future__ import annotations

from collections import defaultdict

from .models import AggregatedResult, ExtractionResult
from .rule_scorer import status_for_score
from .rules_loader import RuleSet


def aggregate_bx_results(results: tuple[ExtractionResult, ...], rules: RuleSet) -> tuple[AggregatedResult, ...]:
    by_bx: dict[str, list[ExtractionResult]] = defaultdict(list)
    for result in results:
        by_bx[result.bx_id].append(result)
    aggregated = []
    boost = rules.common["scores"]["matching_attachment"]
    for bx_id, bx_results in sorted(by_bx.items()):
        dated = [result for result in bx_results if result.order_datetime is not None]
        if not dated:
            aggregated.append(
                AggregatedResult(
                    bx_id,
                    None,
                    None,
                    0.0,
                    "NO_ORDER_DATE",
                    tuple(sorted(result.source_file for result in bx_results)),
                    "所有附件均无可用日期候选",
                    rules.version,
                )
            )
            continue
        order_groups: dict[str, list[ExtractionResult]] = defaultdict(list)
        no_order_number = []
        for result in dated:
            if result.order_number:
                order_groups[result.order_number].append(result)
            else:
                no_order_number.append(result)
        groups = list(order_groups.values())
        by_date: dict[object, list[ExtractionResult]] = defaultdict(list)
        for result in no_order_number:
            by_date[result.order_datetime].append(result)
        groups.extend(by_date.values())
        multiple_unknown_dates = len(by_date) > 1
        for group in groups:
            dates = {result.order_datetime for result in group}
            source_files = tuple(sorted(result.source_file for result in group))
            order_number = group[0].order_number
            if len(dates) > 1:
                aggregated.append(
                    AggregatedResult(
                        bx_id,
                        order_number,
                        None,
                        max(result.confidence_score for result in group),
                        "CONFLICT",
                        source_files,
                        "相同订单号的附件得到不同日期",
                        rules.version,
                    )
                )
                continue
            unique_hashes = {result.file_hash for result in group}
            score = max(result.confidence_score for result in group)
            evidence = group[0].evidence_text
            if len(unique_hashes) > 1:
                score = min(100.0, score + boost)
                evidence += f"; 多附件日期一致 +{boost}"
            status = status_for_score(score, rules)
            if multiple_unknown_dates and order_number is None:
                status = "NEEDS_REVIEW"
                evidence += "; 无订单号且存在多个不同日期"
            if any(result.status == "CONFLICT" for result in group):
                status = "CONFLICT"
            aggregated.append(
                AggregatedResult(
                    bx_id,
                    order_number,
                    next(iter(dates)),
                    score,
                    status,
                    source_files,
                    evidence,
                    rules.version,
                )
            )
    return tuple(aggregated)
