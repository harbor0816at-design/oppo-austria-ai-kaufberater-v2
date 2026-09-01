from app.agent.graph import PresalesWorkflow
from app.agent.guardrails import evaluate
from app.agent.recommender import rank_products
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

    async def search(self, query, confidential_terms, unreleased_names, count=5, **kwargs):
        return [
            PublicSearchResult(
                title="Official competitor page",
                url="https://example.com/official",
                snippet="Publicly released specifications",
            )
        ]


class FakeDeepSeek:
    configured = True

    async def complete(self, messages, **kwargs):
        return "| Product | Battery |\n|---|---|\n| OPPO Test Product | 5000 mAh |"

    async def complete_with_tools(self, messages, tools, executor):
        return await self.complete(messages)


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
            message="Compare this OPPO phone with iPhone 17",
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

class EmptyFactService:
    async def list_active(self, launched_only=False):
        return []

    async def get(self, sku_id):
        return None


class DirectDeepSeek:
    configured = True

    def __init__(self, answer="LTPO dynamically adjusts refresh rate to save power."):
        self.answer = answer
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return self.answer


async def _direct_general_result():
    model = DirectDeepSeek()
    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        EmptyFactService(),
        FakeLeadService(),
        FakeConversationService(),
        FakeSearch(),
        model,
        FakeAudit(),
    )
    result = await workflow.run(
        ChatRequest(
            session_id="direct-session",
            message="What is LTPO and why does it save battery?",
        )
    )
    return result, model


def test_general_question_goes_directly_to_deepseek_without_source_b():
    import asyncio

    result, model = asyncio.run(_direct_general_result())
    assert result.route == "direct"
    assert "LTPO" in result.response_markdown
    assert len(model.calls) == 1
    assert result.cards == []
    system_prompt = model.calls[0][0]["content"]
    assert "PWM/dimming behavior is a separate panel characteristic" in system_prompt


def test_general_technology_comparison_does_not_force_public_search():
    assert PresalesWorkflow.classify_route("Compare OLED vs LCD") == "direct"


def test_competitor_product_question_requires_current_external_search():
    assert PresalesWorkflow.classify_route("What is the battery size of iPhone 17?") == "current_external"


def test_chinese_product_choice_question_uses_grounded_comparison():
    assert (
        PresalesWorkflow.classify_route(
            "OPPO Find X9 和三星 Galaxy S26 怎么选？"
        )
        == "comparison"
    )


def test_chinese_samsung_name_without_galaxy_uses_grounded_comparison():
    assert (
        PresalesWorkflow.classify_route(
            "OPPO Find X9 和三星 S26 怎么选？"
        )
        == "comparison"
    )


def test_english_product_choice_question_uses_grounded_comparison():
    assert (
        PresalesWorkflow.classify_route(
            "OPPO Find X9 or Galaxy S26, which should I choose?"
        )
        == "comparison"
    )


def test_current_news_requires_public_search():
    assert PresalesWorkflow.classify_route("What is the latest smartphone news today?") == "current_external"


def test_youtube_review_request_uses_public_search_before_product_fact_routing():
    assert (
        PresalesWorkflow.classify_route(
            "给我 OPPO Find X9 Pro 的 YouTube 测评链接"
        )
        == "public_review"
    )


def test_german_review_request_uses_public_search():
    assert (
        PresalesWorkflow.classify_route(
            "Zeige mir einen Find X9 Pro Testbericht oder ein Review-Video"
        )
        == "public_review"
    )


def test_public_review_route_executes_live_search_and_returns_sources():
    import asyncio

    class ReviewSearch(FakeSearch):
        def __init__(self):
            self.calls = []

        async def search(self, query, confidential_terms, unreleased_names, count=5, **kwargs):
            self.calls.append(kwargs)
            return await super().search(
                query, confidential_terms, unreleased_names, count=count, **kwargs
            )

    fact = make_fact()
    search = ReviewSearch()
    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        FakeFactService([fact]),
        FakeLeadService(),
        FakeConversationService(),
        search,
        FakeDeepSeek(),
        FakeAudit(),
    )
    result = asyncio.run(
        workflow.run(
            ChatRequest(
                session_id="review-session",
                message="Show me a YouTube review of OPPO Test Product",
            )
        )
    )
    assert result.route == "public_review"
    assert any(card["type"] == "public_sources" for card in result.cards)
    assert search.calls[0]["public_review"] is True


def test_now_buying_request_remains_a_catalog_recommendation():
    assert (
        PresalesWorkflow.classify_route(
            "我预算1000欧元，现在该买哪款 OPPO？"
        )
        == "recommendation"
    )


def test_natural_battery_and_telephoto_needs_rank_find_x9_pro_first():
    find = make_fact().model_copy(
        update={
            "product_name": "OPPO Find X9 Pro",
            "key_features": ["Battery: 7500 mAh", "200 MP telephoto 长焦"],
        }
    )
    reno = make_fact().model_copy(
        update={
            "product_name": "OPPO Reno16 Pro 5G",
            "key_features": ["Battery: 6000 mAh", "50 MP telephoto 长焦"],
        }
    )
    ranked = rank_products(
        "我经常旅行和拍孩子，最怕没电，也想要长焦",
        [reno, find],
    )
    assert ranked[0].product_name == "OPPO Find X9 Pro"


def test_oppo_official_product_fact_requires_source_b():
    fact = make_fact()
    assert PresalesWorkflow.classify_route("What is the OPPO Test Product battery size?", fact) == "official"


def test_buying_request_uses_general_reasoning_plus_source_b_recommendation():
    assert PresalesWorkflow.classify_route("Which OPPO phone is best for battery life?") == "recommendation"

class ExplodingFactService:
    async def list_active(self, launched_only=False):
        raise AssertionError("Source_B should not be touched for this route")

    async def get(self, sku_id):
        raise AssertionError("Source_B should not be touched for this route")


def test_direct_question_does_not_read_source_b():
    import asyncio

    model = DirectDeepSeek("OLED pixels emit their own light.")
    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        ExplodingFactService(),
        FakeLeadService(),
        FakeConversationService(),
        FakeSearch(),
        model,
        FakeAudit(),
    )
    result = asyncio.run(
        workflow.run(
            ChatRequest(
                session_id="lazy-source-b",
                message="Why can OLED display true black?",
            )
        )
    )
    assert result.route == "direct"
    assert "OLED" in result.response_markdown


def test_context_sku_plus_spec_question_is_official():
    assert PresalesWorkflow.classify_route(
        "How big is the battery?",
        has_context_sku=True,
    ) == "official"


def test_link_followup_inherits_recent_brand_context():
    recent = "Compare OPPO Find X9 Pro with Samsung Galaxy S series"
    assert PresalesWorkflow.classify_route(
        "直接给我他们的链接",
        context_text=recent,
    ) == "comparison"


def test_oppo_link_followup_uses_official_source_b():
    recent = "Tell me about OPPO Find X9 Pro"
    assert PresalesWorkflow.classify_route(
        "Give me the official link",
        context_text=recent,
    ) == "official"


def test_austria_specific_esim_and_box_questions_require_source_b():
    assert PresalesWorkflow.classify_route("Does OPPO Find X9 Pro support eSIM?") == "official"
    assert PresalesWorkflow.classify_route("Find X9 Pro charger in box?") == "official"
    assert PresalesWorkflow.classify_route("Find X9 Pro software update years?") == "official"
