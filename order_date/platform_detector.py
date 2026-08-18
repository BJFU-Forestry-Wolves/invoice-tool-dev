from __future__ import annotations

from .models import OCRPage, PlatformDetection
from .rules_loader import RuleSet


def detect_platform(pages: tuple[OCRPage, ...], rules: RuleSet) -> PlatformDetection:
    text = "\n".join(block.normalized_text for page in pages for block in page.blocks).casefold()
    detections = []
    for rule in rules.platforms:
        positives = tuple(keyword for keyword in rule.positive_keywords if keyword.casefold() in text)
        negatives = tuple(keyword for keyword in rule.negative_keywords if keyword.casefold() in text)
        score = len(positives) * 20 - len(negatives) * 25
        detections.append((score, rule, positives, negatives))
    detections.sort(key=lambda item: (-item[0], item[1].platform))
    best_score, best_rule, positives, negatives = detections[0]
    second_score = detections[1][0] if len(detections) > 1 else float("-inf")
    thresholds = rules.common["thresholds"]
    if best_score < thresholds["platform_min_score"] or best_score - second_score < thresholds["platform_tie_delta"]:
        return PlatformDetection("unknown", "未知", float(best_score), positives, negatives, rules.version)
    return PlatformDetection(
        best_rule.platform,
        best_rule.display_name,
        float(best_score),
        positives,
        negatives,
        f"{rules.version}:{best_rule.version}",
    )
