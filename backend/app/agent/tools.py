from __future__ import annotations

from typing import Any

from app.agent.guardrails import confidential_terms
from app.language import Language, locale_for
from app.schemas import LeadSubscribeRequest, ProductFactRead

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_official_products",
            "description": "List active official OPPO products from Source_B.",
            "parameters": {
                "type": "object",
                "properties": {"launched_only": {"type": "boolean"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_official_sku_facts",
            "description": "Get the latest official Source_B facts for one SKU.",
            "parameters": {
                "type": "object",
                "properties": {"sku_id": {"type": "string"}},
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_public_info",
            "description": (
                "Search current public information for released third-party products or "
                "general smartphone technology. Never use for unreleased OPPO products."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subscribe_launch",
            "description": (
                "Record a launch notification only after contact, channel and explicit consent are supplied."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {"type": "string"},
                    "target_sku": {"type": "string"},
                    "channel": {"type": "string", "enum": ["email", "whatsapp"]},
                    "consent_marketing": {"type": "boolean"},
                },
                "required": [
                    "contact",
                    "target_sku",
                    "channel",
                    "consent_marketing",
                ],
            },
        },
    },
]


def safe_fact(fact: ProductFactRead, language: Language | None = None) -> dict[str, Any]:
    data = fact.model_dump(mode="json")
    data.pop("confidential_fields", None)
    if not fact.pricing.is_price_public:
        data["pricing"]["official_price"] = None
    if language and fact.localized_content:
        data["display_content"] = fact.localized_content.get(language, {})
    return data


class ToolExecutor:
    def __init__(
        self,
        fact_service,
        lead_service,
        public_search,
        all_facts: list[ProductFactRead],
        language: Language,
        session_id: str,
        competitor_references: list[dict[str, Any]] | None = None,
        competitor_facts: list[dict[str, Any]] | None = None,
    ):
        self.fact_service = fact_service
        self.lead_service = lead_service
        self.public_search = public_search
        self.all_facts = all_facts
        self.language = language
        self.session_id = session_id
        self.competitor_references = competitor_references or []
        self.competitor_facts = competitor_facts or []
        self.used_public_results: list[dict] = []
        self.created_lead: dict | None = None

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "list_official_products":
            launched_only = bool(arguments.get("launched_only", True))
            facts = await self.fact_service.list_active(launched_only=launched_only)
            return {"products": [safe_fact(fact, self.language) for fact in facts]}

        if name == "get_official_sku_facts":
            fact = await self.fact_service.get(str(arguments.get("sku_id", "")))
            return {"product": safe_fact(fact, self.language) if fact else None}

        if name == "search_public_info":
            unreleased_names = {
                item.product_name
                for item in self.all_facts
                if item.official_status.value != "launched"
            }
            results = await self.public_search.search(
                str(arguments.get("query", "")),
                confidential_terms(self.all_facts),
                unreleased_names,
                official_references=self.competitor_references,
                competitor_facts=self.competitor_facts,
            )
            self.used_public_results = [item.model_dump() for item in results]
            return {
                "results": self.used_public_results,
                "search_available": bool(
                    self.public_search.api_key
                    or self.competitor_references
                    or self.competitor_facts
                ),
                "source_order": [
                    "official_live",
                    "brave_official",
                    "sheet_b_verified_cache",
                    "brave_public",
                ],
            }

        if name == "subscribe_launch":
            request = LeadSubscribeRequest(
                contact=str(arguments.get("contact", "")),
                target_sku=str(arguments.get("target_sku", "")),
                channel=arguments.get("channel", "email"),
                consent_marketing=bool(arguments.get("consent_marketing", False)),
                locale=locale_for(self.language),
                session_id=self.session_id,
            )
            lead = self.lead_service.subscribe(request)
            self.created_lead = lead.model_dump(mode="json")
            return {"lead": self.created_lead}

        return {"error": "unknown_tool"}
