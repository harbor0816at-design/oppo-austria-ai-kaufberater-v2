from app.agent.graph import PresalesWorkflow
from app.agent.guardrails import evaluate
from app.agent.tools import ToolExecutor
from app.cache import HotCache
from app.config import Settings
from app.db import Base, build_engine, build_session_factory
from app.language import tr
from app.schemas import ChatRequest, LeadSubscribeRequest, ProductFactRead, PublicSearchResult
from app.services.leads import LeadService


def make_fact(status="launched", public=True):
    return ProductFactRead.model_validate(
        {
            "sku_id": "TEST-001",
            "product_name": "OPPO Test Product",
            "official_status": status,
            "pricing": {
                "is_price_public": public,
                "official_price": 799 if public else None,
                "early_bird_deposit": None,
                "deposit_discount_value": None,
                "refund_policy": "Official policy",
            },
            "gifts": [],
            "shipping_commitments": {
                "timeline": "Official timeline",
                "regions": ["AT"],
            },
            "key_features": ["5000 mAh battery", "80W charging"],
            "confidential_fields": ["sensor_model", "battery_supplier"],
            "localized_content": {},
            "is_active": True,
        }
    )


def test_unannounced_price_guardrail_does_not_leak():
    fact = make_fact(status="unannounced", public=False)
    blocked, reason, response = evaluate(
        "What will the price of OPPO Test Product be?",
        [fact],
        "en",
        fact,
    )
    assert blocked is True
    assert reason == "unannounced_price"
    assert "799" not in response


class FakeFactService:
    def __init__(self, facts):
        self.facts = facts

    async def list_active(self, launched_only=False):
        if launched_only:
            return [item for item in self.facts if item.official_status.value == "launched"]
        return self.facts

    async def get(self, sku_id):
        return next((item for item in self.facts if item.sku_id == sku_id), None)


class FakeConversationService:
    async def load(self, session_id):
        return {"profile": {}, "messages": [], "language": "en"}

    async def save_turn(self, *args, **kwargs):
        return None


class FakeSearch:
    api_key = "configured"

    async def search(self, query, confidential_terms, unreleased_names, count=5):
        return [
            PublicSearchResult(
                title="Official competitor page",
                url="https://example.com/official",
                snippet="Publicly released specifications",
            )
        ]


class FakeDeepSeek:
    configured = True

    async def complete_with_tools(self, messages, tools, executor, reasoning=False):
        return "| Product | Battery |\n|---|---|\n| OPPO Test Product | 5000 mAh |"


class FakeAudit:
    def record(self, *args, **kwargs):
        return None


class FakeLeadService:
    def subscribe(self, data):
        raise AssertionError("not used")


async def _comparison_result():
    fact = make_fact()
    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        FakeFactService([fact]),
        FakeLeadService(),
        FakeConversationService(),
        FakeSearch(),
        FakeDeepSeek(),
        FakeAudit(),
    )
    return await workflow.run(
        ChatRequest(
            session_id="comparison-session",
            message="Compare this phone with a released competitor",
            context={"sku": fact.sku_id},
        )
    )


def test_competitor_comparison_has_table_and_disclaimer():
    import asyncio

    result = asyncio.run(_comparison_result())
    assert "| Product | Battery |" in result.response_markdown
    assert tr("en", "disclaimer") in result.response_markdown
    assert any(card["type"] == "public_sources" for card in result.cards)


def test_launch_subscription_tool_persists_lead():
    import asyncio

    settings = Settings(database_url="sqlite:///:memory:")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    lead_service = LeadService(factory)

    class NoSearch:
        api_key = None

    executor = ToolExecutor(
        FakeFactService([make_fact()]),
        lead_service,
        NoSearch(),
        [make_fact()],
        "en",
        "lead-session",
    )
    result = asyncio.run(
        executor.execute(
            "subscribe_launch",
            {
                "contact": "test@example.com",
                "target_sku": "TEST-001",
                "channel": "email",
                "consent_marketing": True,
            },
        )
    )
    assert result["lead"]["contact"] == "test@example.com"
    assert len(lead_service.list()) == 1


def test_battery_recommendation_filters_demo_and_prefers_best_launched_product():
    import asyncio

    from app.agent.recommender import rank_products

    demo = make_fact()
    demo.sku_id = "DEMO-001"
    demo.product_name = "OPPO Demo Device (interner Test)"
    demo.key_features = ["9000 mAh battery"]
    standard = make_fact()
    standard.sku_id = "OPPO-A"
    standard.product_name = "OPPO A"
    standard.key_features = ["5000 mAh battery"]
    battery = make_fact()
    battery.sku_id = "OPPO-BATTERY"
    battery.product_name = "OPPO Battery"
    battery.key_features = ["6500 mAh battery", "80W charging"]

    ranked = rank_products(
        "Which OPPO phone is best for battery life?",
        [standard, battery],
    )
    assert ranked[0].sku_id == "OPPO-BATTERY"

    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        FakeFactService([demo, standard, battery]),
        FakeLeadService(),
        FakeConversationService(),
        FakeSearch(),
        FakeDeepSeek(),
        FakeAudit(),
    )
    result = asyncio.run(
        workflow.run(
            ChatRequest(
                session_id="battery-session",
                message="Which OPPO phone is best for battery life?",
            )
        )
    )
    recommendation = next(card for card in result.cards if card["type"] == "recommendation")
    assert recommendation["products"][0]["sku_id"] == "OPPO-BATTERY"
    assert all(not product["sku_id"].startswith("DEMO-") for product in recommendation["products"])


def test_english_official_card_does_not_expose_untranslated_source_b_text():
    fact = make_fact()
    fact.shipping_commitments.timeline = "Deutsche Lieferinformation"
    fact.gifts = []
    workflow = object.__new__(PresalesWorkflow)

    card = workflow._official_card(fact, "en")

    assert card["summary"] == "Official OPPO information"
    assert all(item["value"] != "Deutsche Lieferinformation" for item in card["facts"])
