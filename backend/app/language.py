from __future__ import annotations

import re
from typing import Literal

Language = Literal["de", "en", "zh"]


def detect_language(text: str) -> Language:
    value = text.strip().lower()
    if re.search(r"[\u3400-\u9fff]", value):
        return "zh"

    de_words = re.findall(
        r"\b(?:ich|du|welche|welcher|welches|preis|kamera|akku|möchte|"
        r"brauche|für|mit|kann|versand|lieferung|garantie)\b",
        value,
    )
    en_words = re.findall(
        r"\b(?:which|what|best|price|camera|battery|recommend|compare|"
        r"need|want|with|for|can|shipping|delivery|warranty)\b",
        value,
    )
    de_score = len(de_words) + (2 if re.search(r"[äöüß]", value) else 0)
    return "en" if len(en_words) > de_score else "de"


def locale_for(language: Language) -> str:
    return {"de": "de-AT", "en": "en", "zh": "zh-CN"}[language]


COPY = {
    "de": {
        "catalog_missing": (
            "Aktuell sind noch keine veröffentlichten OPPO Produkte in der "
            "offiziellen Produktdatenbank hinterlegt."
        ),
        "public_unavailable": (
            "Die öffentliche Suche ist derzeit nicht konfiguriert. "
            "Ich erfinde deshalb keine aktuellen Wettbewerbsdaten."
        ),
        "chat_failed": "Die Anfrage konnte gerade nicht abgeschlossen werden. Bitte versuche es erneut.",
        "guardrail_title": "Diese Information ist noch nicht offiziell veröffentlicht.",
        "guardrail_body": (
            "Damit du verlässliche Informationen bekommst, verwende ich keine "
            "Leaks, Gerüchte oder inoffiziellen Preisangaben."
        ),
        "official": "OPPO offizielle Information",
        "status": "Status",
        "price": "Preis",
        "shipping": "Versand",
        "regions": "Regionen",
        "features": "Highlights",
        "gifts": "Geschenke",
        "unannounced": "Noch nicht offiziell veröffentlicht",
        "pre_order": "Vorbestellung",
        "launched": "Verfügbar",
        "disclaimer": (
            "Hinweis: Angaben zu Wettbewerbsprodukten basieren auf öffentlich "
            "verfügbaren Informationen. Maßgeblich sind die jeweils aktuellen "
            "offiziellen Herstellerangaben."
        ),
    },
    "en": {
        "catalog_missing": (
            "No published OPPO products are currently available in the official product database."
        ),
        "public_unavailable": (
            "Public search is not configured right now, so I will not invent current competitor information."
        ),
        "chat_failed": "The request could not be completed right now. Please try again.",
        "guardrail_title": "This information has not been officially published yet.",
        "guardrail_body": (
            "To keep the information reliable, I do not use leaks, rumors or unofficial prices."
        ),
        "official": "Official OPPO information",
        "status": "Status",
        "price": "Price",
        "shipping": "Shipping",
        "regions": "Regions",
        "features": "Highlights",
        "gifts": "Gifts",
        "unannounced": "Not officially published yet",
        "pre_order": "Pre-order",
        "launched": "Available",
        "disclaimer": (
            "Note: Information about competitor products is based on publicly available sources. "
            "The latest official information from each manufacturer takes precedence."
        ),
    },
    "zh": {
        "catalog_missing": "目前官方产品数据库中还没有可用于消费者导购的已发布 OPPO 商品。",
        "public_unavailable": "目前尚未配置独立公网搜索，因此我不会编造最新竞品信息。",
        "chat_failed": "当前暂时无法完成请求，请稍后再试。",
        "guardrail_title": "这项信息尚未官方发布。",
        "guardrail_body": "为了保证信息可靠，我不会使用泄露、爆料、传闻或非官方价格。",
        "official": "OPPO 官方信息",
        "status": "状态",
        "price": "价格",
        "shipping": "发货",
        "regions": "地区",
        "features": "核心亮点",
        "gifts": "赠品",
        "unannounced": "尚未官方发布",
        "pre_order": "预订中",
        "launched": "已上市",
        "disclaimer": "注：竞品参数来自公开网络整理，以品牌官方最新发布为准。",
    },
}


def tr(language: Language, key: str) -> str:
    return COPY[language][key]
