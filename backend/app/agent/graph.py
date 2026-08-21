from __future__ import annotations

import json
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - production installs LangGraph
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.agent.guardrails import evaluate
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.recommender import rank_products
from app.agent.tools import TOOL_SCHEMAS, ToolExecutor, safe_fact
from app.language import Language, detect_language, tr
from app.schemas import AgentResult, ChatRequest, ProductFactRead


class GraphState(TypedDict, total=False):
    request: ChatRequest
    language: Language
    conversation: dict
    all_facts: list[ProductFactRead]
    candidates: list[ProductFactRead]
    requested_fact: ProductFactRead | None
    blocked: bool
    block_reason: str
    response: str
    cards: list[dict[str, Any]]
    route: str


COMPARISON_TERMS = (
    "compare",
    "comparison",
    " vs ",
    "vergleich",
    "对比",
    "竞品",
)
OFFICIAL_TERMS = (
    "price",
    "preis",
    "cost",
    "shipping",
    "versand",
    "delivery",
    "lieferung",
    "gift",
    "warranty",
    "guarantee",
    "garantie",
    "return",
    "refund",
    "价格",
    "发货",
    "赠品",
    "保修",
    "退货",
)
NOTIFY_TERMS = (
    "notify me",
    "launch notification",
    "benachrichtigen",
    "vormerken",
    "开售通知",
    "上市通知",
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
    ):
        self.settings = settings
        self.fact_service = fact_service
        self.lead_service = lead_service
        self.conversation_service = conversation_service
        self.public_search = public_search
        self.deepseek = deepseek
        self.audit_service = audit_service
        self.compiled = self._build_graph()

    def _build_graph(self):
        if StateGraph is None:
            return None
        builder = StateGraph(GraphState)
        builder.add_node("context", self.context_node)
        builder.add_node("guardrail", self.guardrail_node)
        builder.add_node("route", self.router_node)
        builder.add_node("synthesis", self.synthesis_node)
        builder.add_edge(START, "context")
        builder.add_edge("context", "guardrail")
        builder.add_conditional_edges(
            "guardrail",
            lambda state: "blocked" if state.get("blocked") else "continue",
            {"blocked": END, "continue": "route"},
        )
        builder.add_edge("route", "synthesis")
        builder.add_edge("synthesis", END)
        return builder.compile()

    async def context_node(self, state: GraphState) -> GraphState:
        request = state["request"]
        language = detect_language(request.message)
        conversation = await self.conversation_service.load(request.session_id)
        all_facts = [
            fact
            for fact in await self.fact_service.list_active(launched_only=False)
            if not fact.sku_id.upper().startswith("DEMO-")
        ]

        requested_fact = None
        requested_sku = request.context.sku
        if requested_sku and not requested_sku.upper().startswith("DEMO-"):
            requested_fact = await self.fact_service.get(requested_sku)

        launched = [
            fact for fact in all_facts if fact.official_status.value == "launched"
        ]
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
            "language": language,
            "conversation": conversation,
            "all_facts": all_facts,
            "requested_fact": requested_fact,
            "candidates": candidates,
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

    async def router_node(self, state: GraphState) -> GraphState:
        lower = state["request"].message.lower()
        if any(term in lower for term in COMPARISON_TERMS):
            route = "comparison"
        elif any(term in lower for term in NOTIFY_TERMS):
            route = "notify"
        elif any(term in lower for term in OFFICIAL_TERMS):
            route = "official"
        else:
            route = "recommendation"
        self.audit_service.record(
            "chat_router",
            session_id=state["request"].session_id,
            sku_id=(state.get("requested_fact").sku_id if state.get("requested_fact") else None),
            request_text=state["request"].message,
            decision=route,
            payload={"candidate_count": len(state.get("candidates", []))},
        )
        return {**state, "route": route}

    @staticmethod
    def _localized_value(fact: ProductFactRead, language: Language, key: str, fallback):
        block = fact.localized_content.get(language, {}) if fact.localized_content else {}
        if isinstance(block, dict) and block.get(key) not in (None, "", []):
            return block[key]
        return fallback if language == "de" else None

    @staticmethod
    def _localized_features(
        fact: ProductFactRead,
        language: Language,
    ) -> list[str]:
        block = fact.localized_content.get(language, {}) if fact.localized_content else {}
        if isinstance(block, dict) and isinstance(block.get("key_features"), list):
            return [str(item) for item in block["key_features"] if str(item).strip()]
        return list(fact.key_features) if language == "de" else []

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
        shipping_timeline = self._localized_value(
            fact,
            language,
            "shipping_timeline",
            fact.shipping_commitments.timeline,
        )
        if shipping_timeline:
            facts.append(
                {
                    "label": tr(language, "shipping"),
                    "value": shipping_timeline,
                }
            )
        facts.append(
            {
                "label": tr(language, "regions"),
                "value": ", ".join(fact.shipping_commitments.regions),
            }
        )
        localized_gifts = self._localized_value(
            fact,
            language,
            "gifts",
            [item.item_name for item in fact.gifts],
        )
        if localized_gifts:
            facts.append(
                {
                    "label": tr(language, "gifts"),
                    "value": " · ".join(str(item) for item in localized_gifts[:4]),
                }
            )
        return {
            "type": "official_fact",
            "title": fact.product_name,
            "summary": tr(language, "official"),
            "facts": facts,
            "status": fact.official_status.value,
            "product_url": fact.product_url,
            "purchase_url": fact.purchase_url,
        }

    async def synthesis_node(self, state: GraphState) -> GraphState:
        language = state["language"]
        requested = state.get("requested_fact")
        candidates = state.get("candidates", [])
        cards: list[dict[str, Any]] = []

        if not candidates and requested is None:
            return {
                **state,
                "response": tr(language, "catalog_missing"),
                "cards": [],
            }

        focus = requested or candidates[0]
        route = state["route"]

        if route == "recommendation" and candidates:
            launched_candidates = [
                fact for fact in candidates if fact.official_status.value == "launched"
            ]
            if launched_candidates:
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
                                "features": self._localized_features(fact, language)[:3],
                            }
                            for fact in launched_candidates[:3]
                        ],
                    }
                )

        if route == "official" and focus is not None:
            cards.append(self._official_card(focus, language))

        if route == "notify" and focus is not None:
            cards.append(
                {
                    "type": "launch_notification",
                    "target_sku": focus.sku_id,
                    "product_name": focus.product_name,
                }
            )

        executor = ToolExecutor(
            self.fact_service,
            self.lead_service,
            self.public_search,
            state.get("all_facts", []),
            language,
            state["request"].session_id,
        )

        public_context: dict[str, Any] = {
            "search_available": bool(self.public_search.api_key),
            "results": [],
        }
        if route == "comparison":
            try:
                public_context = await executor.execute(
                    "search_public_info", {"query": state["request"].message}
                )
            except Exception as exc:
                public_context = {
                    "search_available": bool(self.public_search.api_key),
                    "results": [],
                    "error": exc.__class__.__name__,
                }

        if not self.deepseek.configured:
            if route == "comparison":
                response = tr(language, "public_unavailable")
            elif focus is None:
                response = tr(language, "catalog_missing")
            else:
                response = {
                    "de": (
                        f"Auf Basis der aktuell bestätigten Produktdaten passt **{focus.product_name}** "
                        "am besten zu deiner Anfrage. Soll ich zusätzlich nach Budget oder Größe eingrenzen?"
                    ),
                    "en": (
                        f"Based on the currently confirmed product data, **{focus.product_name}** "
                        "is the closest match to your request. Should I narrow it further by budget or size?"
                    ),
                    "zh": (
                        f"根据当前已确认的产品信息，**{focus.product_name}** 与你的需求最接近。"
                        "需要我再按预算或尺寸继续筛选吗？"
                    ),
                }[language]
        else:
            conversation = state.get("conversation", {})
            runtime_context = {
                "latest_user_message": state["request"].message,
                "response_language": language,
                "route": route,
                "known_user_profile": conversation.get("profile", {}),
                "selected_product": safe_fact(focus, language) if focus else None,
                "source_b_candidates": [
                    safe_fact(fact, language) for fact in candidates[:8]
                ],
                "source_a": public_context,
            }
            history = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *conversation.get("messages", [])[-12:],
                {
                    "role": "user",
                    "content": (
                        "Answer the latest user message using only this verified runtime context.\n"
                        + json.dumps(runtime_context, ensure_ascii=False)
                    ),
                },
            ]
            response = await self.deepseek.complete_with_tools(
                history,
                TOOL_SCHEMAS,
                executor.execute,
                reasoning=route == "comparison",
            )

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

        if route == "comparison":
            response = response.rstrip() + "\n\n*" + tr(language, "disclaimer") + "*"

        self.audit_service.record(
            "chat_synthesis",
            session_id=state["request"].session_id,
            sku_id=focus.sku_id if focus else None,
            request_text=state["request"].message,
            decision=route,
            payload={"card_count": len(cards)},
        )
        return {**state, "response": response, "cards": cards}

    async def run(self, request: ChatRequest) -> AgentResult:
        state: GraphState = {"request": request, "cards": []}
        if self.compiled is not None:
            result = await self.compiled.ainvoke(state)
        else:
            result = await self.context_node(state)
            result = await self.guardrail_node(result)
            if not result.get("blocked"):
                result = await self.router_node(result)
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
