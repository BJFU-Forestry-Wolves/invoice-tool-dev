from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import DailyMerchantGroup, InvoiceContext, InvoiceIssuerResult, ReviewItem


LIMIT = Decimal("1000")


def _merge_review_items(items: list[ReviewItem]) -> tuple[ReviewItem, ...]:
    merged: dict[tuple[str, str, Decimal | None], dict[str, set]] = {}
    for item in items:
        key = (item.bx_id, item.reason, item.amount)
        bucket = merged.setdefault(key, {"sources": set(), "issuers": set(), "dates": set()})
        bucket["sources"].update(item.source_files)
        bucket["issuers"].update(item.issuer_names)
        bucket["dates"].update(item.order_dates)
    return tuple(
        ReviewItem(
            bx_id,
            tuple(sorted(bucket["sources"])),
            reason,
            tuple(sorted(bucket["issuers"])),
            tuple(sorted(bucket["dates"])),
            amount,
        )
        for (bx_id, reason, amount), bucket in sorted(merged.items(), key=lambda entry: (entry[0][0], entry[0][1]))
    )


def aggregate_daily_merchants(
    results: tuple[InvoiceIssuerResult, ...],
    contexts_by_path: dict[str, tuple[InvoiceContext, ...]],
    limit: Decimal = LIMIT,
) -> tuple[tuple[DailyMerchantGroup, ...], tuple[ReviewItem, ...]]:
    by_record: dict[tuple[str, object], list[tuple[InvoiceIssuerResult, InvoiceContext]]] = defaultdict(list)
    review: list[ReviewItem] = []
    for result in results:
        contexts = contexts_by_path.get(result.source_file.casefold(), ())
        if not contexts:
            review.append(ReviewItem(result.bx_id, (result.source_file,), "发票未在分类清单中找到"))
            continue
        dates = {context.order_date for context in contexts if context.order_date is not None}
        if len(dates) != 1:
            review.append(
                ReviewItem(
                    result.bx_id,
                    (result.source_file,),
                    "缺少唯一订单日期" if not dates else "同一发票关联多个订单日期",
                    (result.issuer_name,) if result.issuer_name else (),
                    tuple(sorted(dates)),
                    contexts[0].amount,
                )
            )
            continue
        context = next(item for item in contexts if item.order_date in dates)
        by_record[(context.bx_id, context.order_date)].append((result, context))

    grouped: dict[tuple[object, str], dict[str, object]] = {}
    for (bx_id, order_date), entries in sorted(by_record.items()):
        usable = [(result, context) for result, context in entries if result.status != "NOT_INVOICE"]
        if not usable:
            review.append(
                ReviewItem(bx_id, tuple(sorted({result.source_file for result, _ in entries})), "未找到可识别的税务发票", (), (order_date,))
            )
            continue
        uncertain = [result for result, _ in usable if result.status != "AUTO_ACCEPTED"]
        issuers = {
            result.normalized_issuer: result.issuer_name
            for result, _ in usable
            if result.normalized_issuer and result.issuer_name
        }
        amounts = {context.amount for _, context in usable if context.amount is not None}
        sources = tuple(sorted({result.source_file for result, _ in usable}))
        if uncertain:
            review.append(
                ReviewItem(
                    bx_id,
                    sources,
                    "至少一份发票的销售方名称未自动确认",
                    tuple(sorted(name for name in issuers.values() if name)),
                    (order_date,),
                    next(iter(amounts)) if len(amounts) == 1 else None,
                )
            )
            continue
        if len(issuers) != 1:
            review.append(
                ReviewItem(
                    bx_id,
                    sources,
                    "同一报销编号识别到多个开票公司，无法分配记录金额",
                    tuple(sorted(name for name in issuers.values() if name)),
                    (order_date,),
                    next(iter(amounts)) if len(amounts) == 1 else None,
                )
            )
            continue
        if len(amounts) != 1:
            review.append(
                ReviewItem(bx_id, sources, "报销金额缺失或不一致", tuple(issuers.values()), (order_date,))
            )
            continue
        normalized, issuer_name = next(iter(issuers.items()))
        amount = next(iter(amounts))
        key = (order_date, normalized)
        bucket = grouped.setdefault(
            key,
            {"issuer_name": issuer_name, "amount": Decimal("0"), "bx_ids": set(), "sources": set()},
        )
        bucket["amount"] += amount
        bucket["bx_ids"].add(bx_id)
        bucket["sources"].update(sources)

    groups = []
    for (order_date, normalized), bucket in sorted(grouped.items()):
        total = bucket["amount"]
        status = "EXCEEDED" if total > limit else "WITHIN_LIMIT"
        bx_ids = tuple(sorted(bucket["bx_ids"]))
        groups.append(
            DailyMerchantGroup(
                order_date,
                bucket["issuer_name"],
                normalized,
                total,
                status,
                bx_ids,
                tuple(sorted(bucket["sources"])),
                f"同日同开票公司 {len(bx_ids)} 个报销编号，合计 {total:.2f} 元",
            )
        )
    return tuple(groups), _merge_review_items(review)
