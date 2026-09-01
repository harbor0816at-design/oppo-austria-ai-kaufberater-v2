import asyncio

from app.services.faq import FAQService, FAQMatch


def test_service_policy_keyword_match_returns_database_answer():
    rows = [
        {
            "Policy_ID": "S004",
            "主题_中文": "保修",
            "Thema_DE": "Garantie",
            "Topic_EN": "Warranty",
            "内容_中文": "oppo.com/at直接购买的手机享3年保修。",
            "Inhalt_DE": "Smartphones direkt von oppo.com/at: 3 Jahre Garantie.",
            "Content_EN": "Smartphones bought directly from oppo.com/at: 3-year warranty.",
            "Source": "https://www.oppo.com/at/",
        }
    ]
    match = FAQService._service_match("官网手机质保多久？", "zh", rows)
    assert match is not None
    assert "3年保修" in match.answer
    assert match.source_id == "S004"


def test_product_fact_match_uses_exact_database_field():
    rows = [
        {
            "Product_ID": "P002",
            "Product_Name": "OPPO Find X9 Pro",
            "Battery": "7500mAh",
            "Charging": "80W SUPERVOOC; 50W AIRVOOC",
            "Official_Source": "https://www.oppo.com/at/find-x9-pro/specs/",
        }
    ]
    match = FAQService._product_match("Find X9 Pro 电池多大？", "", "zh", rows)
    assert match is not None
    assert match.answer == "**OPPO Find X9 Pro:** 7500mAh"
    assert match.match_type == "product_fact"


def test_product_fact_match_returns_all_requested_database_fields():
    rows = [
        {
            "Product_ID": "P002",
            "Product_Name": "OPPO Find X9 Pro",
            "Battery": "7500mAh",
            "Charging": "80W SUPERVOOC; 50W AIRVOOC",
            "Official_Source": "https://www.oppo.com/at/find-x9-pro/specs/",
        }
    ]
    match = FAQService._product_match(
        "Find X9 Pro 的电池和充电规格是什么？",
        "",
        "zh",
        rows,
    )
    assert match is not None
    assert "**电池:** 7500mAh" in match.answer
    assert "**充电:** 80W SUPERVOOC; 50W AIRVOOC" in match.answer


def test_youtube_review_request_bypasses_faq_product_fields():
    service = object.__new__(FAQService)
    match = asyncio.run(
        service.match(
            "给我 OPPO Find X9 Pro 的 YouTube 测评链接",
            "zh",
        )
    )
    assert match is None


def test_compatibility_match_can_answer_iphone_from_ios_limitation():
    rows = [
        {
            "Compatibility_ID": "CM001",
            "OPPO_Product": "OPPO Watch X3",
            "Target_Device_or_OS": "Android smartphones",
            "Compatibility_Type": "OS compatibility",
            "Status": "SUPPORTED",
            "Feature_or_Max_Level": "Full watch setup",
            "限制_中文": "仅支持Android；不支持iOS与Android Go",
            "Einschränkung_DE": "Nur Android; iOS nicht unterstützt",
            "Limitation_EN": "Android only; iOS is not supported",
            "最低系统/条件_中文": "Android 9+",
            "Mindestanforderung_DE": "Android 9+",
            "Minimum_Requirement_EN": "Android 9+",
            "Official_Source": "https://www.oppo.com/at/watch-x3/specs/",
        }
    ]
    match = FAQService._compatibility_match("Watch X3支持iPhone吗？", "", "zh", rows)
    assert match is not None
    assert "不支持iOS" in match.answer


def test_decision_playbook_exact_question_match():
    rows = [
        {
            "Decision_ID": "D006",
            "Consumer_Question_CN": "哪台拍照最好？",
            "Verbraucherfrage_DE": "Welches Smartphone hat die beste Kamera?",
            "Consumer_Question_EN": "Which phone has the best camera?",
            "Decision_Logic_CN": "先追问场景，再结合官方硬件和中立实测。不存在无条件最好。",
            "Entscheidungslogik_DE": "Zuerst das Szenario klären.",
            "Decision_Logic_EN": "Ask the use case first.",
        }
    ]
    match = FAQService._decision_match("哪台拍照最好", "zh", rows)
    assert match is not None
    assert "先追问场景" in match.answer


class FakeFAQService:
    async def match(self, message, language, context_text=""):
        if "warranty" in message.lower():
            return FAQMatch(
                answer="Database warranty answer",
                source_sheet="Service_Policy",
                source_id="S004",
                source_url=None,
                score=100,
                match_type="service_policy",
                matched_terms=["warranty"],
            )
        return None

from app.agent.graph import PresalesWorkflow
from app.config import Settings
from app.schemas import ChatRequest


class _FAQOnly:
    async def match(self, message, language, context_text=""):
        return FAQMatch(
            answer="Database-only answer",
            source_sheet="Service_Policy",
            source_id="S004",
            source_url=None,
            score=100,
            match_type="service_policy",
            matched_terms=["warranty"],
        )


class _NoFacts:
    async def list_active(self, launched_only=False):
        return []

    async def get(self, sku_id):
        return None


class _Conversation:
    async def load(self, session_id):
        return {"profile": {}, "messages": [], "language": "en"}

    async def save_turn(self, *args, **kwargs):
        return None


class _NoSearch:
    api_key = None


class _MustNotCallModel:
    configured = True

    async def complete(self, messages, **kwargs):
        raise AssertionError("DeepSeek must not be called on FAQ hit")


class _Audit:
    def record(self, *args, **kwargs):
        return None


class _Leads:
    pass


def test_faq_hit_bypasses_deepseek_entirely():
    workflow = PresalesWorkflow(
        Settings(database_url="sqlite:///:memory:"),
        _NoFacts(),
        _Leads(),
        _Conversation(),
        _NoSearch(),
        _MustNotCallModel(),
        _Audit(),
        faq_service=_FAQOnly(),
    )
    result = asyncio.run(
        workflow.run(
            ChatRequest(
                session_id="faq-session",
                message="What is the warranty?",
            )
        )
    )
    assert result.route == "faq"
    assert result.response_markdown == "Database-only answer"
    assert any(card["type"] == "faq_source" for card in result.cards)


def test_competitor_fact_query_uses_verified_database_row_but_not_dynamic_price():
    rows = [
        {
            "Competitor_ID": "C005",
            "Brand": "Samsung",
            "Model": "Galaxy S26 Ultra",
            "Battery": "5000mAh",
            "Official_Source": "https://www.samsung.com/at/smartphones/galaxy-s26-ultra/",
        }
    ]
    match = FAQService._competitor_fact_match("Galaxy S26 Ultra battery?", "en", rows)
    assert match is not None
    assert "5000mAh" in match.answer
    assert FAQService._competitor_fact_match("Galaxy S26 Ultra current price?", "en", rows) is None


def test_competitor_fact_does_not_treat_galaxy_name_as_weight_question():
    rows = [
        {
            "Competitor_ID": "C007",
            "Brand": "Samsung",
            "Model": "Galaxy S26",
            "Weight": "167g",
            "Official_Source": "https://www.samsung.com/at/smartphones/galaxy-s26/",
        }
    ]
    assert FAQService._competitor_fact_match("Galaxy S26 怎么样？", "zh", rows) is None


def test_comparison_question_cannot_be_reduced_to_one_competitor_fact():
    rows = [
        {
            "Competitor_ID": "C007",
            "Brand": "Samsung",
            "Model": "Galaxy S26",
            "Weight": "167g",
        }
    ]
    assert (
        FAQService._competitor_fact_match(
            "OPPO Find X9 和 Galaxy S26 怎么选？", "zh", rows
        )
        is None
    )


def test_comparison_map_understands_chinese_buying_intent():
    rows = [
        {
            "Map_ID": "M013",
            "OPPO_Model": "OPPO Find X9",
            "Competitor_Model": "Galaxy S26",
            "OPPO_Wins_CN": "续航和快充",
            "Competitor_Wins_CN": "生态和长期更新",
            "Migration_Risk_CN": "按生态依赖取舍",
        }
    ]
    match = FAQService._comparison_map_match(
        "OPPO Find X9 和 Galaxy S26 怎么选？", "", "zh", rows
    )
    assert match is not None
    assert match.source_id == "M013"
    assert "续航和快充" in match.answer


def test_comparison_map_understands_samsung_name_without_galaxy():
    rows = [
        {
            "Map_ID": "M013",
            "OPPO_Model": "OPPO Find X9",
            "Competitor_Model": "Galaxy S26",
            "OPPO_Wins_CN": "续航和快充",
            "Competitor_Wins_CN": "生态和长期更新",
            "Migration_Risk_CN": "按生态依赖取舍",
        }
    ]
    match = FAQService._comparison_map_match(
        "OPPO Find X9 和三星 S26 怎么选？", "", "zh", rows
    )
    assert match is not None
    assert match.source_id == "M013"
