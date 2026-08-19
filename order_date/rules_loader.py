from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RULE_ENGINE_VERSION = "5"


@dataclass(frozen=True, slots=True)
class PlatformRule:
    platform: str
    display_name: str
    version: str
    positive_keywords: tuple[str, ...]
    negative_keywords: tuple[str, ...]
    order_date_labels: tuple[str, ...]
    weak_order_date_labels: tuple[str, ...]
    excluded_date_labels: tuple[str, ...]
    order_number_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    version: str
    common: dict[str, Any]
    platforms: tuple[PlatformRule, ...]


def load_rules(rules_dir: Path) -> RuleSet:
    paths = sorted(rules_dir.glob("*.json"), key=lambda path: path.name)
    if not paths:
        raise FileNotFoundError(f"规则目录中没有 JSON 文件: {rules_dir}")
    digest = hashlib.sha256()
    digest.update(f"rule_engine={RULE_ENGINE_VERSION}\0".encode())
    values = {}
    for path in paths:
        content = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(content)
        values[path.stem] = json.loads(content.decode("utf-8"))
    common = values.pop("common")
    platforms = tuple(
        PlatformRule(
            platform=value["platform"],
            display_name=value["display_name"],
            version=value["version"],
            positive_keywords=tuple(value["positive_keywords"]),
            negative_keywords=tuple(value["negative_keywords"]),
            order_date_labels=tuple(value["order_date_labels"]),
            weak_order_date_labels=tuple(value["weak_order_date_labels"]),
            excluded_date_labels=tuple(value["excluded_date_labels"]),
            order_number_patterns=tuple(value["order_number_patterns"]),
        )
        for _, value in sorted(values.items())
    )
    return RuleSet(f"{common['version']}+{digest.hexdigest()[:12]}", common, platforms)
