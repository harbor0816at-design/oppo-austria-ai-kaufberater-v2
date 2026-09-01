from __future__ import annotations

import re

from app.schemas import ProductFactRead

GROUPS = {
    "battery": (
        (
            "battery",
            "akku",
            "续航",
            "电池",
            "没电",
            "电量",
            "续航焦虑",
            "travel",
            "reise",
            "旅行",
        ),
        ("battery", "akku", "mah", "续航", "电池"),
    ),
    "charging": (
        ("charge", "charging", "laden", "充电", "快充"),
        ("charge", "charging", "supervooc", "laden", "w", "充电", "快充"),
    ),
    "camera": (
        (
            "camera",
            "photo",
            "kamera",
            "foto",
            "portrait",
            "telephoto",
            "zoom",
            "kids",
            "children",
            "影像",
            "拍照",
            "相机",
            "长焦",
            "变焦",
            "孩子",
        ),
        (
            "camera",
            "photo",
            "kamera",
            "zoom",
            "telephoto",
            "periscope",
            "portrait",
            "影像",
            "拍照",
            "相机",
            "长焦",
            "变焦",
            "潜望",
        ),
    ),
    "gaming": (
        ("game", "gaming", "spiel", "游戏"),
        ("game", "gaming", "cooling", "fps", "游戏", "散热"),
    ),
    "compact": (
        ("compact", "small", "kompakt", "klein", "小屏", "轻"),
        ("compact", "small", "kompakt", "light", "小屏", "轻"),
    ),
}


def score_product(query: str, fact: ProductFactRead, profile: dict | None = None) -> float:
    lower = query.lower()
    localized_text = " ".join(
        str(value)
        for language_block in fact.localized_content.values()
        if isinstance(language_block, dict)
        for value in language_block.values()
        if isinstance(value, (str, int, float))
    )
    haystack = " ".join(
        [fact.product_name, *fact.key_features, localized_text]
    ).lower()
    score = 0.0

    for query_terms, feature_terms in GROUPS.values():
        if any(term in lower for term in query_terms):
            score += 4 * sum(1 for term in feature_terms if term in haystack)

    if any(
        term in lower
        for term in (
            "battery",
            "akku",
            "续航",
            "电池",
            "没电",
            "电量",
            "续航焦虑",
            "travel",
            "reise",
            "旅行",
        )
    ):
        values = [
            int(value)
            for value in re.findall(r"(\d{4,5})\s*m?ah", haystack, re.I)
        ]
        if values:
            score += max(values) / 1000

    if any(term in lower for term in ("charge", "charging", "laden", "充电", "快充")):
        values = [
            int(value) for value in re.findall(r"(\d{2,3})\s*w\b", haystack, re.I)
        ]
        if values:
            score += max(values) / 20

    budget_match = re.search(
        r"(?:€\s*|max(?:imal)?\s*)(\d{3,4})"
        r"|(?:budget|preis|price|预算)[^\d]{0,12}(\d{3,4})",
        lower,
    )
    budget = None
    if budget_match:
        budget = int(next(group for group in budget_match.groups() if group))
    elif profile and isinstance(profile.get("budget"), int):
        budget = profile["budget"]

    if budget is not None and fact.pricing.official_price is not None:
        if fact.pricing.official_price <= budget:
            score += 6
        else:
            score -= (fact.pricing.official_price - budget) / 100

    return score


def rank_products(
    query: str,
    facts: list[ProductFactRead],
    profile: dict | None = None,
) -> list[ProductFactRead]:
    return sorted(
        facts,
        key=lambda fact: (
            score_product(query, fact, profile),
            fact.product_name.lower(),
        ),
        reverse=True,
    )
