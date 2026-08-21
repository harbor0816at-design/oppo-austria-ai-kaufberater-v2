from app.services.google_sheets import GoogleSheetsSource


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
