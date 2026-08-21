from __future__ import annotations

import re

from app.language import Language, tr
from app.schemas import ProductFactRead

PRICE_RE = re.compile(
    r"\b(?:price|preis|msrp|rrp|uvp|cost)\b|价格|售价|多少钱|€|EUR",
    re.I,
)
LEAK_RE = re.compile(
    r"\b(?:leak|leaked|rumou?r|spy shot|prototype|gerücht|geleakt)\b|"
    r"爆料|泄露|谍照|工程机",
    re.I,
)


def confidential_terms(facts: list[ProductFactRead]) -> set[str]:
    aliases = {
        "sensor_model": [
            "sensor model",
            "camera sensor",
            "sensormodell",
            "kamerasensor",
            "传感器型号",
        ],
        "battery_supplier": [
            "battery supplier",
            "cell supplier",
            "batterielieferant",
            "电池供应商",
            "电芯供应商",
        ],
        "bom_cost": ["bom cost", "materialkosten", "物料成本", "bom成本"],
    }
    terms: set[str] = set()
    for fact in facts:
        for field in fact.confidential_fields:
            normalized = field.strip().lower()
            terms.add(normalized)
            terms.add(normalized.replace("_", " "))
            terms.update(item.lower() for item in aliases.get(normalized, []))
    return {item for item in terms if item}


def evaluate(
    message: str,
    facts: list[ProductFactRead],
    language: Language,
    focus_fact: ProductFactRead | None = None,
) -> tuple[bool, str, str]:
    lower = message.lower()
    if any(term in lower for term in confidential_terms(facts)):
        return True, "confidential_field", tr(language, "guardrail_body")

    unreleased = [
        fact for fact in facts if fact.official_status.value != "launched"
    ]
    # Any OPPO leak/rumor request is blocked even if Source_B is temporarily unavailable.
    if LEAK_RE.search(message) and (
        unreleased
        or re.search(r"\boppo\b|\bfind\s*x\d|\breno\s*\d", message, re.I)
    ):
        return True, "unreleased_leak", tr(language, "guardrail_body")

    if (
        focus_fact is not None
        and focus_fact.official_status.value != "launched"
        and PRICE_RE.search(message)
        and not focus_fact.pricing.is_price_public
    ):
        return True, "unannounced_price", tr(language, "guardrail_body")

    for fact in unreleased:
        mentions_product = (
            fact.product_name.lower() in lower or fact.sku_id.lower() in lower
        )
        if (
            mentions_product
            and PRICE_RE.search(message)
            and not fact.pricing.is_price_public
        ):
            return True, "unannounced_price", tr(language, "guardrail_body")

    return False, "", ""
