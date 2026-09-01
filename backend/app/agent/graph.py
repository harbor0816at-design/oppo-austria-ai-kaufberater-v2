from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - production installs LangGraph
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.agent.guardrails import evaluate
from app.agent.prompts import ROUTE_INSTRUCTIONS, SYSTEM_PROMPT
from app.agent.recommender import rank_products
from app.agent.tools import ToolExecutor, safe_fact
from app.language import Language, detect_language, tr
from app.schemas import AgentResult, ChatRequest, ProductFactRead


class GraphState(TypedDict, total=False):
    request: ChatRequest
    language: Language
    conversation: dict
    all_facts: list[ProductFactRead]
    candidates: list[ProductFactRead]
    requested_fact: ProductFactRead | None
    source_b_error: str | None
    source_b_context: dict[str, Any]
    faq_match: dict[str, Any] | None
    blocked: bool
    block_reason: str
    response: str
    cards: list[dict[str, Any]]
    route: str


COMPARE_RE = re.compile(
    r"\b(?:compare|comparison|versus|vs\.?|vergleich|gegenüber|"
    r"which(?:\s+\w+){0,5}\s+(?:better|choose|buy)|better\s+choice)\b|"
    r"对比|比较|相比|哪个好|哪个更|怎么选|如何选|选哪个|该选|区别|差异",
    re.I,
)
NOTIFY_RE = re.compile(
    r"\b(?:notify me|launch notification|benachrichtigen|vormerken|remind me)\b|"
    r"开售通知|上市通知|到货通知|提醒我",
    re.I,
)

LINK_REQUEST_RE = re.compile(
    r"\b(?:link|links|url|website|webpage|product page|buy link|purchase link|official page|"
    r"webseite|produktseite|kauf-link|offizielle seite)\b|链接|网址|购买页|商品页|官网链接|直接链接",
    re.I,
)

PUBLIC_REVIEW_RE = re.compile(
    r"\b(?:youtube|youtu\.be|video\s+review|review\s+video|reviews?|hands[- ]on|"
    r"unboxing|testbericht|erfahrungsbericht|praxistest)\b|"
    r"测评|评测|开箱|体验视频|实测视频|测评视频|评测视频",
    re.I,
)

OPPO_RE = re.compile(
    r"(?<![0-9a-z])(?:oppo|find\s*x\d|reno\s*\d|coloros|supervooc|airvooc|"
    r"enco|watch\s*x|oppo\s*pad)(?![0-9a-z])",
    re.I,
)

OFFICIAL_FACT_RE = re.compile(
    r"\b(?:price|cost|msrp|rrp|uvp|preis|spec|specs|specification|battery|mah|"
    r"charging|charge|camera|sensor|chip|chipset|processor|display|screen|storage|ram|"
    r"stock|availability|available|shipping|delivery|gift|promotion|promo|coupon|warranty|"
    r"guarantee|return|refund|launch|release|official|weight|dimension|waterproof|ip\d+|"
    r"esim|e-sim|nfc|wi-?fi|wifi|coloros|android version|os version|software update|"
    r"security update|update years|box contents|in the box|charger included|charger in box|"
    r"brightness|nits|refresh rate|hz|battery cycle|charge cycles|5g bands?|network bands?|"
    r"produktseite|kaufseite|offizielle seite|lieferumfang|ladegerät|aktualisierung|updates?)\b|"
    r"价格|售价|多少钱|参数|配置|电池|续航|充电|快充|相机|摄像头|芯片|处理器|屏幕|存储|内存|"
    r"库存|有货|发货|配送|赠品|促销|优惠|优惠券|保修|质保|退货|退款|上市|发布|重量|尺寸|防水|"
    r"eSIM|NFC|无线网络|系统版本|软件更新|安全更新|包装清单|盒内|充电器|亮度|刷新率|充电循环|"
    r"5G频段|网络频段|购买链接|产品链接|官网",
    re.I,
)

RECOMMEND_RE = re.compile(
    r"\b(?:recommend|recommendation|which\s+(?:oppo\s+)?(?:phone|smartphone)|"
    r"best\s+(?:oppo\s+)?(?:phone|smartphone)|looking\s+for\s+(?:a\s+)?(?:phone|smartphone)|"
    r"need\s+(?:a\s+)?(?:phone|smartphone)|buy(?:ing)?\s+(?:a\s+)?(?:phone|smartphone)|"
    r"empfehlen|welches\s+(?:oppo\s+)?(?:handy|smartphone)|suche\s+(?:ein\s+)?(?:handy|smartphone)|"
    r"bestes\s+(?:handy|smartphone))\b|推荐|哪款\s*(?:手机|OPPO)|什么手机|买手机|"
    r"(?:该|应该)?买哪款|预算.{0,20}(?:OPPO|手机)|适合我的手机|选手机",
    re.I,
)

EXTERNAL_BRAND_RE = re.compile(
    r"\b(?:apple|iphone|samsung|galaxy|xiaomi|redmi|poco|honor|google\s*pixel|pixel|"
    r"oneplus|nothing\s*phone|motorola|huawei|sony\s*xperia|realme)\b|"
    r"苹果|三星|小米|红米|荣耀|谷歌(?:\s*Pixel)?|一加|摩托罗拉|华为|索尼|真我",
    re.I,
)

CURRENT_EXTERNAL_RE = re.compile(
    r"\b(?:latest|current|today|now|recent|news|newest|just released|price today|current price|"
    r"market price|availability today|weather|exchange rate|stock price|breaking)\b|"
    r"最新|现在|今天|目前|近期|新闻|刚发布|实时|当前价格|市场价格|天气|汇率|"
    r"aktuell|heute|neueste|nachrichten|derzeit|momentan|wetter|wechselkurs",
    re.I,
)

GENERAL_TECH_COMPARE_RE = re.compile(
    r"\b(?:oled|lcd|ltpo|amoled|ips|wifi|bluetooth|android|ios|camera|battery|charging)\b",
    re.I,
)

DETAILED_SPECS_RE = re.compile(
    r"\b(?:spec|specs|specification|specifications|technical\s+data|full\s+details|"
    r"datenblatt|technische\s+daten|vollständige\s+daten)\b|"
    r"参数|规格|配置|详细参数|完整参数|参数表|配置表",
    re.I,
)


class PresalesWorkflow:
    def __init__(
        self,
        settings,
        fact_service,
        lead_service,
        conversation_service,
        public_search,
        deepseek,
        audit_service,
        faq_service=None,
    ):
        self.settings = settings
        self.fact_service = fact_service
        self.lead_service = lead_service
        self.conversation_service = conversation_service
        self.public_search = public_search
        self.deepseek = deepseek
        self.audit_service = audit_service
        self.faq_service = faq_service
        self.compiled = self._build_graph()

    def _build_graph(self):
        if StateGraph is None:
            return None
        builder = StateGraph(GraphState)
        builder.add_node("context", self.context_node)
        builder.add_node("route", self.router_node)
        builder.add_node("grounding", self.source_grounding_node)
        builder.add_node("guardrail", self.guardrail_node)
        builder.add_node("synthesis", self.synthesis_node)
        builder.add_edge(START, "context")
        builder.add_edge("context", "route")
        builder.add_edge("route", "grounding")
        builder.add_edge("grounding", "guardrail")
        builder.add_conditional_edges(
            "guardrail",
            lambda state: "blocked" if state.get("blocked") else "continue",
            {"blocked": END, "continue": "synthesis"},
        )
        builder.add_edge("synthesis", END)
        return builder.compile()

    @staticmethod
    def _mentioned_fact(message: str, facts: list[ProductFactRead]) -> ProductFactRead | None:
        lower = message.lower()
        # Prefer the longest product name to avoid Find X9 matching Find X9 Pro.
        for fact in sorted(facts, key=lambda item: len(item.product_name), reverse=True):
            names = {fact.product_name.lower(), fact.sku_id.lower()}
            if fact.product_name.lower().startswith("oppo "):
                names.add(fact.product_name[5:].lower())
            if any(name and name in lower for name in names):
                return fact
        return None

    async def context_node(self, state: GraphState) -> GraphState:
        request = state["request"]
        language = detect_language(request.message)
        conversation = await self.conversation_service.load(request.session_id)

        # FAQ is the first answer layer. A conservative keyword/product match returns
        # the database text verbatim and bypasses DeepSeek. Only a miss proceeds to
        # the normal DeepSeek + Source_B/public-source workflow.
        faq_match = None
        # Review/video discovery is a public-search request even when the message
        # also contains camera/video vocabulary present in Product_KB.
        if self.faq_service is not None and not PUBLIC_REVIEW_RE.search(request.message):
            recent_context = " ".join(
                str(item.get("content", ""))
                for item in conversation.get("messages", [])[-6:]
            )
            try:
                match = await self.faq_service.match(
                    request.message, language, recent_context
                )
                faq_match = match.to_dict() if match is not None else None
            except Exception:
                # FAQ failure must not break the advisor; it simply falls through.
                faq_match = None

        # Source_B is loaded lazily only after FAQ miss + route classification.
        return {
            **state,
            "language": language,
            "conversation": conversation,
            "all_facts": [],
            "candidates": [],
            "requested_fact": None,
            "source_b_error": None,
            "source_b_context": {},
            "faq_match": faq_match,
        }

    async def source_grounding_node(self, state: GraphState) -> GraphState:
        route = state.get("route", "direct")
        if route not in {
            "official",
            "recommendation",
            "comparison",
            "notify",
            "current_external",
            "public_review",
        }:
            return state

        request = state["request"]
        conversation = state.get("conversation", {})
        source_b_error = None
        try:
            context_loader = getattr(self.fact_service, "source_context", None)
            source_b_context = (
                await context_loader(state["language"]) if callable(context_loader) else {}
            )
            # Competitor-only current-external turns need curated official references and
            # verified competitor facts, but do not need to load the OPPO product catalog.
            all_facts = (
                []
                if route == "current_external"
                else await self.fact_service.list_active(launched_only=False)
            )
        except Exception as exc:
            all_facts = []
            source_b_context = {}
            source_b_error = exc.__class__.__name__

        requested_fact = None
        requested_sku = request.context.sku
        if requested_sku and not requested_sku.upper().startswith("DEMO-"):
            try:
                requested_fact = await self.fact_service.get(requested_sku)
            except Exception:
                requested_fact = None
        if requested_fact is None:
            recent_context = " ".join(
                str(item.get("content", ""))
                for item in conversation.get("messages", [])[-6:]
            )
            requested_fact = self._mentioned_fact(
                request.message + " " + recent_context, all_facts
            )

        launched = [fact for fact in all_facts if fact.official_status.value == "launched"]
        candidates = rank_products(
            request.message,
            launched,
            conversation.get("profile", {}),
        )[:8]
        if requested_fact and requested_fact.official_status.value == "launched":
            candidates = [requested_fact] + [
                fact for fact in candidates if fact.sku_id != requested_fact.sku_id
            ]
        elif requested_fact and not candidates:
            candidates = [requested_fact]

        return {
            **state,
            "all_facts": all_facts,
            "requested_fact": requested_fact,
            "candidates": candidates,
            "source_b_error": source_b_error,
            "source_b_context": source_b_context,
        }

    async def guardrail_node(self, state: GraphState) -> GraphState:
        blocked, reason, response = evaluate(
            state["request"].message,
            state.get("all_facts", []),
            state["language"],
            state.get("requested_fact"),
        )
        if not blocked:
            return {**state, "blocked": False}

        requested = state.get("requested_fact")
        self.audit_service.record(
            "chat_guardrail",
            session_id=state["request"].session_id,
            sku_id=requested.sku_id if requested else None,
            request_text=state["request"].message,
            decision="blocked",
            payload={"reason": reason},
        )
        return {
            **state,
            "blocked": True,
            "block_reason": reason,
            "response": response,
            "route": "blocked",
            "cards": [
                {
                    "type": "guardrail",
                    "title": tr(state["language"], "guardrail_title"),
                    "message": tr(state["language"], "guardrail_body"),
                    "target_sku": requested.sku_id if requested else None,
                }
            ],
        }

    @staticmethod
    def classify_route(
        message: str,
        requested_fact: ProductFactRead | None = None,
        has_context_sku: bool = False,
        context_text: str = "",
    ) -> str:
        """Classify only the *source policy* needed for a turn.

        DeepSeek remains the conversational brain. This router only decides whether
        current facts must be grounded in Source_B or public search before synthesis.
        """
        if NOTIFY_RE.search(message):
            return "notify"

        # Independent reviews and videos require live public discovery. This must
        # precede generic link and product-field routing.
        if PUBLIC_REVIEW_RE.search(message):
            return "public_review"

        has_external_brand = bool(EXTERNAL_BRAND_RE.search(message))
        has_oppo = bool(OPPO_RE.search(message)) or requested_fact is not None or has_context_sku
        has_compare = bool(COMPARE_RE.search(message))

        # Short follow-ups such as “give me their links” inherit only the recent
        # product/brand context needed to resolve which source should provide URLs.
        if LINK_REQUEST_RE.search(message):
            combined = f"{message} {context_text}"
            contextual_external = bool(EXTERNAL_BRAND_RE.search(combined))
            contextual_oppo = bool(OPPO_RE.search(combined)) or has_context_sku
            if contextual_external and contextual_oppo:
                return "comparison"
            if contextual_external:
                return "current_external"
            if contextual_oppo:
                return "official"

        # Product-vs-product comparisons involving competitors need both sources.
        if has_external_brand and has_oppo and (
            has_compare or DETAILED_SPECS_RE.search(message)
        ):
            return "comparison"

        # General technology comparisons such as OLED vs LCD are stable knowledge.
        if has_compare and not has_external_brand and GENERAL_TECH_COMPARE_RE.search(message):
            return "direct"

        # Any competitor product claim is treated as external/current for accuracy.
        if has_external_brand:
            return "current_external"

        # Buying intent uses DeepSeek reasoning plus the current OPPO catalog. It
        # must win over generic time words such as "now" / "现在该买".
        if RECOMMEND_RE.search(message):
            return "recommendation"

        # Time-sensitive facts (news, weather, current market info) require live search.
        if CURRENT_EXTERNAL_RE.search(message):
            # OPPO store facts such as today's OPPO price remain Source_B-authoritative.
            if has_oppo and OFFICIAL_FACT_RE.search(message):
                return "official"
            return "current_external"

        # Exact/current OPPO product facts must come from Source_B.
        if has_oppo and OFFICIAL_FACT_RE.search(message):
            return "official"

        # Everything else goes straight to DeepSeek general capability.
        return "direct"

    async def router_node(self, state: GraphState) -> GraphState:
        if state.get("faq_match"):
            match = state["faq_match"]
            self.audit_service.record(
                "chat_router",
                session_id=state["request"].session_id,
                sku_id=None,
                request_text=state["request"].message,
                decision="faq",
                payload={
                    "faq_source_sheet": match.get("source_sheet"),
                    "faq_source_id": match.get("source_id"),
                    "faq_match_type": match.get("match_type"),
                    "faq_score": match.get("score"),
                },
            )
            return {**state, "route": "faq"}

        recent_context = " ".join(
            str(item.get("content", ""))
            for item in state.get("conversation", {}).get("messages", [])[-6:]
        )
        route = self.classify_route(
            state["request"].message,
            state.get("requested_fact"),
            bool(state["request"].context.sku),
            recent_context,
        )
        self.audit_service.record(
            "chat_router",
            session_id=state["request"].session_id,
            sku_id=(
                state.get("requested_fact").sku_id
                if state.get("requested_fact")
                else None
            ),
            request_text=state["request"].message,
            decision=route,
            payload={
                "candidate_count": len(state.get("candidates", [])),
                "source_b_available": not bool(state.get("source_b_error")),
                "brave_search_configured": bool(self.public_search.api_key),
            },
        )
        return {**state, "route": route}

    @staticmethod
    def _localized_value(fact: ProductFactRead, language: Language, key: str, fallback):
        block = fact.localized_content.get(language, {}) if fact.localized_content else {}
        return block.get(key, fallback) if isinstance(block, dict) else fallback

    def _official_card(self, fact: ProductFactRead, language: Language) -> dict[str, Any]:
        facts = [
            {
                "label": tr(language, "status"),
                "value": tr(language, fact.official_status.value),
            }
        ]
        if fact.pricing.is_price_public and fact.pricing.official_price is not None:
            facts.append(
                {
                    "label": tr(language, "price"),
                    "value": f"€{fact.pricing.official_price:.2f}",
                }
            )
        facts.append(
            {
                "label": tr(language, "shipping"),
                "value": self._localized_value(
                    fact,
                    language,
                    "shipping_timeline",
                    fact.shipping_commitments.timeline,
                ),
            }
        )
        facts.append(
            {
                "label": tr(language, "regions"),
                "value": ", ".join(fact.shipping_commitments.regions),
            }
        )
        if fact.gifts:
            facts.append(
                {
                    "label": tr(language, "gifts"),
                    "value": " · ".join(item.item_name for item in fact.gifts[:4]),
                }
            )
        source_meta = (fact.localized_content or {}).get("_source_b", {})
        return {
            "type": "official_fact",
            "title": fact.product_name,
            "summary": tr(language, "official"),
            "facts": facts,
            "status": fact.official_status.value,
            "product_url": fact.product_url,
            "purchase_url": fact.purchase_url,
            "official_specs_url": source_meta.get("official_specs_url"),
            "verified_source_url": source_meta.get("verified_source_url"),
        }

    @staticmethod
    def _fallback_no_model(language: Language, route: str) -> str:
        copy = {
            "de": "Der AI-Dienst ist derzeit nicht verfügbar. Bitte versuche es später erneut.",
            "en": "The AI service is currently unavailable. Please try again later.",
            "zh": "AI 服务当前暂不可用，请稍后再试。",
        }
        if route in {"current_external", "comparison", "public_review"}:
            return tr(language, "public_unavailable")
        return copy[language]

    async def synthesis_node(self, state: GraphState) -> GraphState:
        language = state["language"]
        route = state["route"]

        # FAQ hit: return the database answer directly. No DeepSeek rewrite, no model
        # completion and no public search. This preserves the exact maintained wording.
        if route == "faq" and state.get("faq_match"):
            match = state["faq_match"]
            response = str(match.get("answer", "")).strip()
            source_url = match.get("source_url")
            if source_url:
                label = {"zh": "来源", "de": "Quelle", "en": "Source"}[language]
                response = response.rstrip() + f"\n\n[{label}]({source_url})"
            cards = [
                {
                    "type": "faq_source",
                    "source_sheet": match.get("source_sheet"),
                    "source_id": match.get("source_id"),
                    "match_type": match.get("match_type"),
                    "source_url": source_url,
                }
            ]
            self.audit_service.record(
                "chat_synthesis",
                session_id=state["request"].session_id,
                sku_id=None,
                request_text=state["request"].message,
                decision="faq",
                payload={
                    "faq_hit": True,
                    "faq_source_sheet": match.get("source_sheet"),
                    "faq_source_id": match.get("source_id"),
                    "deepseek_used": False,
                },
            )
            return {**state, "response": response, "cards": cards}

        requested = state.get("requested_fact")
        candidates = state.get("candidates", [])
        all_facts = state.get("all_facts", [])
        cards: list[dict[str, Any]] = []

        focus = requested or (candidates[0] if candidates else None)
        question = state["request"].message

        # Current official OPPO facts may never fall back to model memory.
        if route == "official" and not all_facts:
            return {
                **state,
                "response": tr(language, "catalog_missing"),
                "cards": [],
            }

        # Recommendation cards are only created from live Source_B products.
        if route == "recommendation" and candidates:
            cards.append(
                {
                    "type": "recommendation",
                    "products": [
                        {
                            "sku_id": fact.sku_id,
                            "product_name": fact.product_name,
                            "price": (
                                fact.pricing.official_price
                                if fact.pricing.is_price_public
                                else None
                            ),
                            "status": fact.official_status.value,
                            "product_url": fact.product_url,
                            "purchase_url": fact.purchase_url,
                            "features": (
                                fact.localized_content.get(language, {}).get(
                                    "key_features", fact.key_features
                                )[:3]
                                if isinstance(
                                    fact.localized_content.get(language, {}), dict
                                )
                                else fact.key_features[:3]
                            ),
                        }
                        for fact in candidates[:3]
                    ],
                }
            )

        # Show a fact card only for a specific product rather than dumping the catalog.
        if route == "official" and requested is not None:
            cards.append(self._official_card(requested, language))

        if route == "notify" and focus is not None:
            cards.append(
                {
                    "type": "launch_notification",
                    "target_sku": focus.sku_id,
                    "product_name": focus.product_name,
                }
            )

        source_b_non_product = state.get("source_b_context", {})
        competitor_references = source_b_non_product.get("competitor_references", [])
        competitor_facts = source_b_non_product.get("competitor_facts", [])
        executor = ToolExecutor(
            self.fact_service,
            self.lead_service,
            self.public_search,
            all_facts,
            language,
            state["request"].session_id,
            competitor_references=competitor_references,
            competitor_facts=competitor_facts,
        )

        # Public search is deterministic for recency-sensitive questions. DeepSeek then
        # remains responsible for understanding and synthesizing the answer.
        public_context: dict[str, Any] = {
            "search_available": bool(
                self.public_search.api_key
                or competitor_references
                or competitor_facts
            ),
            "results": [],
            "source_order": [
                "official_live",
                "brave_official",
                "sheet_b_verified_cache",
                "brave_public",
            ],
        }
        if route in {"current_external", "comparison", "public_review"}:
            search_query = question
            if LINK_REQUEST_RE.search(question):
                prior_user_turns = [
                    str(item.get("content", ""))
                    for item in state.get("conversation", {}).get("messages", [])[-8:]
                    if item.get("role") == "user"
                ]
                if prior_user_turns:
                    search_query = " ".join(prior_user_turns[-2:] + [question])[:1200]
            try:
                public_context = await executor.execute(
                    "search_public_info",
                    {
                        "query": search_query,
                        "public_review": route == "public_review",
                    },
                )
            except Exception as exc:
                public_context = {
                    "search_available": bool(
                        self.public_search.api_key
                        or competitor_references
                        or competitor_facts
                    ),
                    "results": [],
                    "error": exc.__class__.__name__,
                    "source_order": [
                        "official_live",
                        "brave_official",
                        "sheet_b_verified_cache",
                        "brave_public",
                    ],
                }

        if not self.deepseek.configured:
            response = self._fallback_no_model(language, route)
        else:
            conversation = state.get("conversation", {})
            source_b_context = []
            if route in {
                "official",
                "recommendation",
                "comparison",
                "notify",
                "public_review",
            }:
                source_b_context = [safe_fact(fact, language) for fact in candidates[:8]]
                if requested and all(
                    item.get("sku_id") != requested.sku_id for item in source_b_context
                ):
                    source_b_context.insert(0, safe_fact(requested, language))

            runtime_context = {
                "current_date_utc": datetime.now(timezone.utc).date().isoformat(),
                "latest_user_message": question,
                "response_language": language,
                "source_policy": route,
                "route_instruction": ROUTE_INSTRUCTIONS[route],
                "known_user_profile": conversation.get("profile", {}),
                "source_b_available": bool(all_facts),
                "source_b_selected_product": (
                    safe_fact(focus, language)
                    if focus
                    and route
                    in {"official", "recommendation", "comparison", "notify", "public_review"}
                    else None
                ),
                "source_b_candidates": source_b_context,
                "source_b_rules_and_services": state.get("source_b_context", {}),
                "verified_product_names": {
                    "oppo": sorted(
                        {
                            fact.product_name
                            for fact in candidates
                            if fact.product_name
                        }
                    ),
                    "competitors": sorted(
                        {
                            str(item.get("product_name", "")).strip()
                            for item in competitor_facts
                            if str(item.get("product_name", "")).strip()
                        }
                    ),
                },
                "release_status_policy": (
                    "A product present in supplied Source_B, FAQ, official-public, or verified "
                    "competitor evidence must not be described as unannounced or unreleased. "
                    "Do not infer launch status from model training dates."
                ),
                "link_requested": bool(LINK_REQUEST_RE.search(question)),
                "public_search": public_context,
            }

            history = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *conversation.get("messages", [])[-12:],
                {
                    "role": "user",
                    "content": (
                        f"{ROUTE_INSTRUCTIONS[route]}\n\n"
                        "Runtime grounding context follows. AI is only the explanation and presentation layer "
                        "for product facts. Never add, estimate, round, or normalize an OPPO specification that "
                        "is not explicitly present in Source_B. If a verified URL is supplied and the user asks "
                        "for a link, output that URL as a clickable Markdown link.\n"
                        + json.dumps(runtime_context, ensure_ascii=False)
                    ),
                },
            ]

            # Direct/general questions go straight to DeepSeek with no tool constraint.
            # Other modes are also synthesized by DeepSeek after deterministic grounding.
            response = await self.deepseek.complete(history)

        if executor.used_public_results:
            cards.append(
                {
                    "type": "public_sources",
                    "sources": [
                        {"title": item["title"], "url": item["url"]}
                        for item in executor.used_public_results
                    ],
                }
            )

        if route == "comparison" and executor.used_public_results:
            response = response.rstrip() + "\n\n*" + tr(language, "disclaimer") + "*"

        self.audit_service.record(
            "chat_synthesis",
            session_id=state["request"].session_id,
            sku_id=focus.sku_id if focus else None,
            request_text=question,
            decision=route,
            payload={
                "card_count": len(cards),
                "source_b_used": route
                in {"official", "recommendation", "comparison", "notify", "public_review"},
                "public_search_used": bool(executor.used_public_results),
                "deepseek_direct": route == "direct",
            },
        )
        return {**state, "response": response, "cards": cards}

    async def run(self, request: ChatRequest) -> AgentResult:
        state: GraphState = {"request": request, "cards": []}
        if self.compiled is not None:
            result = await self.compiled.ainvoke(state)
        else:
            result = await self.context_node(state)
            result = await self.router_node(result)
            result = await self.source_grounding_node(result)
            result = await self.guardrail_node(result)
            if not result.get("blocked"):
                result = await self.synthesis_node(result)
        response = result.get("response", "")
        await self.conversation_service.save_turn(
            request.session_id,
            result.get("language", "de"),
            request.message,
            response,
        )
        return AgentResult(
            response_markdown=response,
            cards=result.get("cards", []),
            route=result.get("route", "blocked"),
            blocked=bool(result.get("blocked")),
        )
