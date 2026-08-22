from __future__ import annotations

import re

from app.agent.recommender import rank_products
from app.language import Language, tr
from app.schemas import AgentResult, ChatRequest, ProductFactRead


QUICK_INTENT_EXPANSIONS = {
    "相机": "我最看重手机相机，请根据当前 OPPO 已上市机型帮我推荐，并说明影像差异。",
    "续航": "我最看重手机续航，请根据当前 OPPO 已上市机型帮我推荐，并说明电池和充电差异。",
    "价格": "我最看重价格，请根据当前 OPPO 已上市机型和可公开的官方价格信息帮我推荐；如果价格未公开，请不要猜。",
    "机型对比": "我想比较当前 OPPO 已上市机型。请先推荐适合比较的机型，并问我想比较哪两款。",
    "我还不确定": "我还不确定适合哪款 OPPO 手机，请根据我的需求一步一步帮我选择。",
    "kamera": "Ich lege besonders viel Wert auf die Kamera. Empfehle mir passende aktuell verfügbare OPPO Smartphones und erkläre die Kamera-Unterschiede.",
    "akku": "Ich lege besonders viel Wert auf die Akkulaufzeit. Empfehle mir passende aktuell verfügbare OPPO Smartphones und erkläre Akku- und Lade-Unterschiede.",
    "preis": "Der Preis ist mir besonders wichtig. Empfehle mir anhand der aktuell verfügbaren OPPO Smartphones und nur öffentlich bestätigter Preise passende Modelle; nicht veröffentlichte Preise bitte nicht schätzen.",
    "modelle vergleichen": "Welches aktuelle OPPO Smartphone passt zu mir? Ich möchte anschließend zwei OPPO Modelle vergleichen; zeige mir zuerst sinnvolle Kandidaten.",
    "ich weiß noch nicht": "Ich weiß noch nicht, welches OPPO Smartphone zu mir passt. Hilf mir Schritt für Schritt anhand meiner Anforderungen.",
    "camera": "Camera quality matters most to me. Recommend suitable current OPPO smartphones and explain the camera differences.",
    "battery": "Battery life matters most to me. Recommend suitable current OPPO smartphones and explain the battery and charging differences.",
    "price": "Price matters most to me. Recommend from current OPPO smartphones using only publicly confirmed official prices; do not guess unpublished prices.",
    "compare models": "Which current OPPO smartphone should I consider? I want to compare two OPPO models, so show me sensible candidates first.",
    "i’m not sure yet": "I am not sure which OPPO smartphone suits me. Help me choose step by step based on my needs.",
    "i'm not sure yet": "I am not sure which OPPO smartphone suits me. Help me choose step by step based on my needs.",
}

PRICE_RE = re.compile(r"\b(?:price|preis|cost|budget)\b|价格|售价|多少钱", re.I)
CAMERA_RE = re.compile(r"\b(?:camera|kamera|photo|foto|portrait|zoom)\b|相机|影像|拍照|摄像头", re.I)
BATTERY_RE = re.compile(r"\b(?:battery|akku|charging|charge|laden)\b|续航|电池|充电|快充", re.I)
COMPARE_RE = re.compile(r"\b(?:compare|comparison|vergleich)\b|对比|比较", re.I)
UNSURE_RE = re.compile(r"not sure|weiß noch nicht|还不确定|不知道选", re.I)


def expand_quick_intent(message: str) -> str:
    value = str(message or "").strip()
    return QUICK_INTENT_EXPANSIONS.get(value.casefold(), value)


def _status_value(fact: ProductFactRead) -> str:
    value = getattr(fact.official_status, "value", fact.official_status)
    return str(value)


def _localized_features(fact: ProductFactRead, language: Language) -> list[str]:
    block = fact.localized_content.get(language, {}) if fact.localized_content else {}
    if isinstance(block, dict):
        values = block.get("key_features")
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()]
    return [str(item) for item in (fact.key_features or []) if str(item).strip()]


def _mentioned_fact(message: str, facts: list[ProductFactRead]) -> ProductFactRead | None:
    lower = message.lower()
    for fact in sorted(facts, key=lambda item: len(item.product_name), reverse=True):
        aliases = {fact.product_name.lower(), fact.sku_id.lower()}
        if fact.product_name.lower().startswith("oppo "):
            aliases.add(fact.product_name[5:].lower())
        if any(alias and alias in lower for alias in aliases):
            return fact
    return None


def _official_card(fact: ProductFactRead, language: Language) -> dict:
    status = _status_value(fact)
    facts = [{"label": tr(language, "status"), "value": tr(language, status)}]
    if fact.pricing.is_price_public and fact.pricing.official_price is not None:
        facts.append({"label": tr(language, "price"), "value": f"€{fact.pricing.official_price:.2f}"})
    facts.append({"label": tr(language, "shipping"), "value": fact.shipping_commitments.timeline})
    facts.append({"label": tr(language, "regions"), "value": ", ".join(fact.shipping_commitments.regions)})
    return {
        "type": "official_fact",
        "title": fact.product_name,
        "summary": tr(language, "official"),
        "facts": facts,
        "status": status,
        "product_url": fact.product_url,
        "purchase_url": fact.purchase_url,
    }


def _recommendation_card(facts: list[ProductFactRead], language: Language) -> dict:
    products = []
    for fact in facts[:3]:
        products.append(
            {
                "sku_id": fact.sku_id,
                "product_name": fact.product_name,
                "price": fact.pricing.official_price if fact.pricing.is_price_public else None,
                "status": _status_value(fact),
                "product_url": fact.product_url,
                "purchase_url": fact.purchase_url,
                "features": _localized_features(fact, language)[:3],
            }
        )
    return {"type": "recommendation", "products": products}


def _feature_matches(fact: ProductFactRead, language: Language, pattern: re.Pattern) -> list[str]:
    features = _localized_features(fact, language)
    matches = [item for item in features if pattern.search(item)]
    return (matches or features)[:4]


def _localized_copy(language: Language, key: str) -> str:
    copy = {
        "zh": {
            "price_missing": "当前官方产品数据没有公开可确认的价格，我不会猜测。请以 OPPO 奥地利官网或结账页面的实时价格为准。",
            "compare": "可以比较的当前 OPPO 机型包括：{models}。告诉我你最想比较的两款，我会按相机、续航、性能、屏幕等维度整理。",
            "unsure": "可以。我先问一个最有用的问题：你下一部手机最看重相机、续航、性能、尺寸，还是预算？",
            "generic": "AI 服务刚才出现短暂波动，但官方产品数据仍可用。你可以继续问具体型号、相机、续航、充电、价格或机型对比。",
            "camera": "如果你最看重相机，我会优先看这些当前 OPPO 机型：",
            "battery": "如果你最看重续航，我会优先看这些当前 OPPO 机型：",
            "price": "当前可公开确认价格的 OPPO 机型：",
        },
        "de": {
            "price_missing": "In den offiziellen Produktdaten ist aktuell kein bestätigter Preis veröffentlicht. Ich schätze deshalb keinen Preis. Maßgeblich ist der aktuelle Preis im OPPO Österreich Shop bzw. Checkout.",
            "compare": "Aktuell lassen sich unter anderem diese OPPO Modelle vergleichen: {models}. Nenne mir zwei Modelle, dann vergleiche ich Kamera, Akku, Leistung und Display.",
            "unsure": "Gerne. Eine Frage hilft am meisten: Was ist dir wichtiger – Kamera, Akku, Leistung, Größe oder Budget?",
            "generic": "Der AI-Dienst hatte gerade eine kurze Störung, die offiziellen Produktdaten sind aber verfügbar. Du kannst nach einem Modell, Kamera, Akku, Laden, Preis oder einem Vergleich fragen.",
            "camera": "Wenn die Kamera am wichtigsten ist, würde ich zuerst diese aktuellen OPPO Modelle ansehen:",
            "battery": "Wenn die Akkulaufzeit am wichtigsten ist, würde ich zuerst diese aktuellen OPPO Modelle ansehen:",
            "price": "Aktuell öffentlich bestätigte OPPO Preise:",
        },
        "en": {
            "price_missing": "The official product data does not currently contain a confirmed public price, so I will not guess. Please use the current OPPO Austria shop or checkout price.",
            "compare": "Current OPPO models you can compare include: {models}. Tell me which two you want, and I will compare camera, battery, performance and display.",
            "unsure": "Sure. One question helps most: what matters more to you — camera, battery, performance, size, or budget?",
            "generic": "The AI service had a brief interruption, but the official product data is still available. You can ask about a model, camera, battery, charging, price, or a comparison.",
            "camera": "If camera quality matters most, I would start with these current OPPO models:",
            "battery": "If battery life matters most, I would start with these current OPPO models:",
            "price": "Current publicly confirmed OPPO prices:",
        },
    }
    return copy[language][key]


async def build_degraded_result(
    request: ChatRequest,
    language: Language,
    fact_service,
) -> AgentResult:
    try:
        facts = await fact_service.list_active(launched_only=False)
    except Exception:
        facts = []

    launched = [fact for fact in facts if _status_value(fact) == "launched"]
    question = request.message.strip()
    focus = _mentioned_fact(question, facts)
    cards: list[dict] = []

    if focus is not None:
        cards.append(_official_card(focus, language))
        if PRICE_RE.search(question):
            if focus.pricing.is_price_public and focus.pricing.official_price is not None:
                response = f"**{focus.product_name}**: €{focus.pricing.official_price:.2f}"
            else:
                response = f"**{focus.product_name}**\n\n{_localized_copy(language, 'price_missing')}"
            return AgentResult(response_markdown=response, cards=cards, route="degraded")

        pattern = CAMERA_RE if CAMERA_RE.search(question) else BATTERY_RE if BATTERY_RE.search(question) else None
        selected = _feature_matches(focus, language, pattern) if pattern else _localized_features(focus, language)[:4]
        if selected:
            response = f"**{focus.product_name}**\n\n" + "\n".join(f"- {item}" for item in selected)
        else:
            response = f"**{focus.product_name}**\n\n{_localized_copy(language, 'generic')}"
        return AgentResult(response_markdown=response, cards=cards, route="degraded")

    if COMPARE_RE.search(question):
        models = ", ".join(fact.product_name for fact in launched[:6])
        response = _localized_copy(language, "compare").format(models=models or "OPPO")
        return AgentResult(response_markdown=response, cards=[], route="degraded")

    if UNSURE_RE.search(question):
        return AgentResult(
            response_markdown=_localized_copy(language, "unsure"),
            cards=[],
            route="degraded",
        )

    if PRICE_RE.search(question):
        priced = [
            fact for fact in launched
            if fact.pricing.is_price_public and fact.pricing.official_price is not None
        ]
        if not priced:
            return AgentResult(
                response_markdown=_localized_copy(language, "price_missing"),
                cards=[],
                route="degraded",
            )
        priced.sort(key=lambda fact: fact.pricing.official_price or 0)
        response = _localized_copy(language, "price") + "\n\n" + "\n".join(
            f"- **{fact.product_name}**: €{fact.pricing.official_price:.2f}"
            for fact in priced[:6]
        )
        return AgentResult(
            response_markdown=response,
            cards=[_recommendation_card(priced, language)],
            route="degraded",
        )

    if CAMERA_RE.search(question) or BATTERY_RE.search(question):
        ranked = rank_products(question, launched, {})[:3]
        if ranked:
            kind = "camera" if CAMERA_RE.search(question) else "battery"
            pattern = CAMERA_RE if kind == "camera" else BATTERY_RE
            lines = [_localized_copy(language, kind), ""]
            for fact in ranked:
                features = _feature_matches(fact, language, pattern)[:2]
                detail = " · ".join(features)
                lines.append(f"- **{fact.product_name}**" + (f": {detail}" if detail else ""))
            return AgentResult(
                response_markdown="\n".join(lines),
                cards=[_recommendation_card(ranked, language)],
                route="degraded",
            )

    return AgentResult(
        response_markdown=_localized_copy(language, "generic"),
        cards=[],
        route="degraded",
    )
