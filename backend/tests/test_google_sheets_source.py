import base64
import json

from app.services.google_sheets import GoogleSheetsSource


def _source(raw=None, raw_b64=None):
    return GoogleSheetsSource(
        "sheet-id",
        raw,
        raw_b64,
        "Products!A1:B2",
        "Promotions!A1:B2",
        "Services!A1:B2",
    )


def test_google_sheet_credentials_report_missing_without_exposing_values():
    source = _source()
    assert source.configured is False
    assert source.credential_status == {
        "json_present": False,
        "base64_present": False,
        "selected_source": None,
        "parsed": False,
        "error": "credentials_missing",
        "source_errors": {},
    }


def test_google_sheet_credentials_report_invalid_base64():
    source = _source(raw_b64="not-valid-base64!")
    assert source.configured is False
    assert source.credential_status["base64_present"] is True
    assert source.credential_status["error"] == "all_credentials_invalid"
    assert source.credential_status["source_errors"] == {
        "base64": "invalid_base64",
    }


def test_google_sheet_credentials_accept_json_and_base64():
    payload = json.dumps({
        "client_email": "reader@example.iam.gserviceaccount.com",
        "private_key": "private-key-placeholder",
    })
    raw_source = _source(raw=payload)
    b64_source = _source(raw_b64=base64.b64encode(payload.encode()).decode())

    assert raw_source.configured is True
    assert raw_source.credential_status["selected_source"] == "json"
    assert raw_source.credential_status["error"] is None
    assert b64_source.configured is True
    assert b64_source.credential_status["selected_source"] == "base64"
    assert b64_source.credential_status["error"] is None


def test_google_sheet_credentials_fall_back_to_base64_when_json_is_invalid():
    payload = json.dumps({
        "client_email": "reader@example.iam.gserviceaccount.com",
        "private_key": "private-key-placeholder",
    })
    source = _source(
        raw="not-json",
        raw_b64=base64.b64encode(payload.encode()).decode(),
    )

    assert source.configured is True
    assert source.credential_status["selected_source"] == "base64"
    assert source.credential_status["error"] is None
    assert source.credential_status["source_errors"] == {
        "json": "invalid_json",
    }


def test_google_sheet_parser_builds_product_fact():
    products = [{
        "sku_id": "AT-TEST",
        "product_name": "OPPO Test",
        "official_status": "launched",
        "is_active": True,
        "price_public": False,
        "battery_mah": 7000,
        "wired_charging_w": 80,
        "regions": "AT,DE",
        "shipping_timeline_de": "Versand aus Österreich",
        "key_features_de": "7000-mAh-Akku | 80 W SUPERVOOC",
        "key_features_en": "7000 mAh battery | 80 W SUPERVOOC",
        "key_features_zh": "7000mAh 电池 | 80W SUPERVOOC",
        "return_policy_de": "30 Tage Rückgabe",
    }]
    result = GoogleSheetsSource.parse_catalog(products, [], [])
    assert result.errors == []
    assert len(result.products) == 1
    fact = result.products[0]
    assert fact.sku_id == "AT-TEST"
    assert fact.pricing.is_price_public is False
    assert "Battery: 7000 mAh" in fact.key_features
    assert fact.shipping_commitments.regions == ["AT", "DE"]


def test_google_sheet_parser_skips_inactive_rows():
    products = [{
        "sku_id": "AT-OFF",
        "product_name": "Off",
        "official_status": "launched",
        "is_active": False,
    }]
    result = GoogleSheetsSource.parse_catalog(products, [], [])
    assert result.products == []


def test_google_sheet_parser_exposes_exact_at_source_b_metadata_and_policies():
    products = [{
        "sku_id": "AT-X9P",
        "product_name": "OPPO Find X9 Pro",
        "official_status": "launched",
        "is_active": True,
        "regions": "AT,DE",
        "return_policy_de": "30 Tage Rückgabe",
        "battery_mah": 7500,
        "official_model_code": "CPH2791",
        "market_scope": "AT/EU",
        "display_resolution": "FHD+ 2772×1272",
        "ltpo_status": "Not stated on OPPO Austria official specs",
        "esim_support": "Yes",
        "official_specs_url": "https://www.oppo.com/at/smartphones/series-find-x/find-x9-pro/specs/",
        "ai_may_infer_missing_facts": False,
        "exact_fact_policy": "exact_or_unknown",
    }]
    knowledge = [{
        "faq_id": "POLICY-AT-002",
        "category": "system_policy",
        "active": True,
        "question_en": "May AI estimate missing product facts?",
        "answer_en": "No. Exact product facts must come from Source_B.",
        "market": "AT",
    }]
    result = GoogleSheetsSource.parse_catalog(products, [], [], knowledge)
    assert result.errors == []
    meta = result.products[0].localized_content["_source_b"]
    assert meta["official_facts"]["official_model_code"] == "CPH2791"
    assert meta["official_facts"]["ltpo_status"].startswith("Not stated")
    assert meta["official_facts"]["ai_may_infer_missing_facts"] is False
    assert meta["exact_fact_policy"] == "exact_or_unknown"
    assert len(result.knowledge) == 1


def test_google_sheet_parser_exposes_verified_competitor_facts():
    competitor_facts = [{
        "competitor_id": "AT-SAMSUNG-S26U",
        "brand": "Samsung",
        "product_name": "Samsung Galaxy S26 Ultra",
        "market": "AT",
        "is_active": True,
        "battery_mah": 5000,
        "official_specs_url": "https://www.samsung.com/at/smartphones/galaxy-s26-ultra/specs/",
        "verified_at": "2026-08-26",
        "ai_may_infer_missing_facts": False,
    }]
    result = GoogleSheetsSource.parse_catalog([], [], [], [], [], competitor_facts)
    assert len(result.competitor_facts) == 1
    assert result.competitor_facts[0]["battery_mah"] == 5000
    assert result.competitor_facts[0]["market"] == "AT"
