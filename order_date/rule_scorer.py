from __future__ import annotations

from dataclasses import replace
from .models import DateCandidate, OCRPage, PlatformDetection, ScoredCandidate
from .rules_loader import PlatformRule, RuleSet


def _bounds(block) -> tuple[float, float, float, float]:
    xs = [point[0] for point in block.polygon]
    ys = [point[1] for point in block.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _relation(label_block, candidate_blocks, spatial) -> str | None:
    lx1, ly1, lx2, ly2 = _bounds(label_block)
    boxes = [_bounds(block) for block in candidate_blocks]
    cx1, cy1 = min(box[0] for box in boxes), min(box[1] for box in boxes)
    cx2, cy2 = max(box[2] for box in boxes), max(box[3] for box in boxes)
    label_height = max(1.0, ly2 - ly1)
    candidate_height = max(1.0, cy2 - cy1)
    label_center_y = (ly1 + ly2) / 2
    candidate_center_y = (cy1 + cy2) / 2
    same_line = abs(label_center_y - candidate_center_y) <= max(label_height, candidate_height) * spatial[
        "same_line_height_factor"
    ]
    if same_line and cx1 >= lx1 and cx1 - lx2 <= label_height * spatial["same_line_max_distance_factor"]:
        return "same_line_right"
    label_center_x = (lx1 + lx2) / 2
    candidate_center_x = (cx1 + cx2) / 2
    if (
        cy1 >= ly1
        and cy1 - ly2 <= label_height * spatial["below_max_vertical_factor"]
        and abs(candidate_center_x - label_center_x) <= label_height * spatial["below_max_horizontal_factor"]
    ):
        return "below_label"
    return None


def score_candidates(
    pages: tuple[OCRPage, ...],
    candidates: tuple[DateCandidate, ...],
    platform: PlatformDetection,
    platform_rule: PlatformRule | None,
    rules: RuleSet,
) -> tuple[ScoredCandidate, ...]:
    blocks = tuple(block for page in pages for block in page.blocks)
    common = rules.common
    scores = common["scores"]
    spatial = common["spatial"]
    strong_labels = tuple(platform_rule.order_date_labels if platform_rule else ()) + tuple(
        common["strong_order_date_labels"]
    )
    weak_labels = tuple(platform_rule.weak_order_date_labels if platform_rule else ()) + tuple(
        common["weak_order_date_labels"]
    )
    excluded_labels = tuple(platform_rule.excluded_date_labels if platform_rule else ()) + tuple(
        common["excluded_date_labels"]
    )
    results = []
    for candidate in candidates:
        value = float(scores["valid_full_date"])
        reasons = [f"完整日期 +{scores['valid_full_date']}"]
        candidate_blocks = tuple(blocks[index] for index in candidate.source_block_indexes)
        chosen_label = None
        relation = None
        label_strength = None
        for labels, strength in ((strong_labels, "strong"), (weak_labels, "weak")):
            for label in dict.fromkeys(labels):
                direct = any(label in block.normalized_text for block in candidate_blocks)
                matching_blocks = [block for block in blocks if block.page_index == candidate.page_index and label in block.normalized_text]
                found_relation = "same_line_right" if direct else next(
                    (_relation(block, candidate_blocks, spatial) for block in matching_blocks if _relation(block, candidate_blocks, spatial)),
                    None,
                )
                if found_relation:
                    chosen_label, relation, label_strength = label, found_relation, strength
                    break
            if chosen_label:
                break
        if chosen_label:
            label_score = scores["exact_label"] if label_strength == "strong" else scores["weak_label"]
            value += label_score + scores[relation]
            reasons.extend((f"标签 {chosen_label} +{label_score}", f"空间关系 {relation} +{scores[relation]}"))
            candidate = replace(candidate, label=chosen_label)
        negative_hits = []
        for label in dict.fromkeys(excluded_labels):
            for block in blocks:
                if block.page_index != candidate.page_index or label not in block.normalized_text:
                    continue
                negative_spatial = {**spatial, "same_line_max_distance_factor": spatial["negative_nearby_factor"]}
                negative_relation = _relation(block, candidate_blocks, negative_spatial)
                if not negative_relation:
                    continue
                # A date explicitly paired with a positive label on the same row belongs to
                # that row.  Timeline labels from earlier rows may still fall inside the
                # deliberately generous "below" window, but must not penalize this date.
                if relation == "same_line_right" and negative_relation == "below_label":
                    continue
                negative_hits.append(label)
                break
        authoritative_labels = set(common["authoritative_order_date_labels"])
        if chosen_label in authoritative_labels and relation == "same_line_right":
            negative_hits = []
        if negative_hits:
            value += scores["excluded_label"]
            reasons.append(f"排除标签 {','.join(negative_hits)} {scores['excluded_label']}")
        if platform.platform == "unknown":
            value += scores["unknown_platform"]
            reasons.append(f"未知平台 {scores['unknown_platform']}")
        else:
            value += scores["known_platform"]
            reasons.append(f"平台 {platform.platform} +{scores['known_platform']}")
        if candidate.has_seconds:
            value += scores["seconds_precision"]
            reasons.append(f"精确到秒 +{scores['seconds_precision']}")
        if candidate.ocr_confidence >= 0.85:
            value += scores["high_ocr_confidence"]
            reasons.append(f"OCR高置信 +{scores['high_ocr_confidence']}")
        if candidate.corrected:
            value += scores["ocr_correction"]
            reasons.append(f"OCR字符修正 {scores['ocr_correction']}")
        results.append(ScoredCandidate(candidate, max(0.0, min(100.0, value)), tuple(reasons), tuple(negative_hits)))
    return tuple(sorted(results, key=lambda item: (-item.score, item.candidate.normalized_datetime)))


def status_for_score(score: float, rules: RuleSet) -> str:
    thresholds = rules.common["thresholds"]
    if score >= thresholds["auto_accept"]:
        return "AUTO_ACCEPTED"
    if score >= thresholds["needs_review"]:
        return "NEEDS_REVIEW"
    return "NO_ORDER_DATE"
