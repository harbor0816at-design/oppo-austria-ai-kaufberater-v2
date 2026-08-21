import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import LeadSubscribeRequest, PricingSchema, ProductFactSchema


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


def test_email_subscription_normalizes_contact():
    lead = LeadSubscribeRequest(
        contact=" Buyer@Example.COM ",
        target_sku="TEST-001",
        channel="email",
        consent_marketing=True,
    )
    assert lead.contact == "buyer@example.com"


def test_invalid_whatsapp_contact_is_rejected():
    with pytest.raises(ValidationError):
        LeadSubscribeRequest(
            contact="not-a-phone",
            target_sku="TEST-001",
            channel="whatsapp",
            consent_marketing=True,
        )


def test_default_admin_key_is_not_production_safe():
    settings = Settings(app_env="production", admin_api_key="change-me")
    assert settings.admin_key_secure is False
