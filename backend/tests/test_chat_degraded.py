import asyncio

from app.agent.degraded import build_degraded_result, expand_quick_intent
from app.schemas import ChatRequest, ProductFactRead


def make_fact(name: str, sku: str, features: list[str], public_price: float | None = None):
    return ProductFactRead.model_validate(
        {
            "sku_id": sku,
            "product_name": name,
            "official_status": "launched",
            "pricing": {
                "is_price_public": public_price is not None,
                "official_price": public_price,
                "early_bird_deposit": None,
                "deposit_discount_value": None,
                "refund_policy": "Official policy",
            },
            "gifts": [],
            "shipping_commitments": {
                "timeline": "Versand aus Österreich",
                "regions": ["AT", "DE"],
            },
            "key_features": features,
            "confidential_fields": [],
            "localized_content": {
                "zh": {"key_features": features},
                "de": {"key_features": features},
                "en": {"key_features": features},
            },
            "is_active": True,
        }
    )


class FakeFactService:
    def __init__(self):
        self.facts = [
            make_fact(
                "OPPO Find X9 Ultra",
                "AT-FIND-X9-ULTRA",
                [
                    "Battery: 7050 mAh",
                    "Camera: Dual 200 MP Hasselblad cameras",
                    "50 MP 10x optical telephoto",
                ],
            ),
            make_fact(
                "OPPO Find X9 Pro",
                "AT-FIND-X9-PRO",
                [
                    "Battery: 7500 mAh",
                    "Camera: 200 MP Hasselblad telephoto",
                    "80 W SUPERVOOC",
                ],
            ),
        ]

    async def list_active(self, launched_only=False):
        return self.facts



def test_quick_reply_expands_to_oppo_buying_intent():
    expanded = expand_quick_intent("相机")
    assert expanded != "相机"
    assert "OPPO" in expanded
    assert "推荐" in expanded



def test_camera_degraded_response_uses_official_products_instead_of_error():
    result = asyncio.run(
        build_degraded_result(
            ChatRequest(session_id="camera", message="相机"),
            "zh",
            FakeFactService(),
        )
    )
    assert result.route == "degraded"
    assert "OPPO" in result.response_markdown
    assert "无法加载回答" not in result.response_markdown
    assert any(card["type"] == "recommendation" for card in result.cards)



def test_price_degraded_response_never_guesses_unpublished_price():
    result = asyncio.run(
        build_degraded_result(
            ChatRequest(session_id="price", message="价格"),
            "zh",
            FakeFactService(),
        )
    )
    assert result.route == "degraded"
    assert "不会猜" in result.response_markdown
    assert "€" not in result.response_markdown



def test_specific_product_degraded_response_is_grounded():
    result = asyncio.run(
        build_degraded_result(
            ChatRequest(session_id="product", message="OPPO Find X9 Ultra 相机"),
            "zh",
            FakeFactService(),
        )
    )
    assert "OPPO Find X9 Ultra" in result.response_markdown
    assert "200 MP" in result.response_markdown
    assert any(card["type"] == "official_fact" for card in result.cards)
