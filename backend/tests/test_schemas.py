import pytest
from pydantic import ValidationError

from app.schemas import PricingSchema, ProductFactSchema


def base_product():
    return {
        "sku_id": "TEST-001",
        "product_name": "OPPO Test Product",
        "official_status": "launched",
        "pricing": {
            "is_price_public": True,
            "official_price": 799,
            "early_bird_deposit": None,
            "deposit_discount_value": None,
            "refund_policy": "Official policy",
        },
        "gifts": [],
        "shipping_commitments": {
            "timeline": "Official timeline",
            "regions": ["at", "de"],
        },
        "key_features": ["5000 mAh battery"],
        "confidential_fields": ["sensor_model"],
    }


def test_private_price_is_forced_to_none():
    value = PricingSchema(
        is_price_public=False,
        official_price=999,
        early_bird_deposit=None,
        deposit_discount_value=None,
        refund_policy="Official policy",
    )
    assert value.official_price is None


def test_preorder_deposit_must_be_less_than_discount():
    data = base_product()
    data["official_status"] = "pre_order"
    data["pricing"].update(
        {
            "is_price_public": False,
            "official_price": None,
            "early_bird_deposit": 100,
            "deposit_discount_value": 50,
        }
    )
    with pytest.raises(ValidationError):
        ProductFactSchema.model_validate(data)


def test_launched_product_may_have_no_deposit():
    fact = ProductFactSchema.model_validate(base_product())
    assert fact.pricing.early_bird_deposit is None
    assert fact.shipping_commitments.regions == ["AT", "DE"]
