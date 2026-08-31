from __future__ import annotations

from app.schemas import ProductFactRead
from app.services.facts import FactService


FALLBACK_PRODUCTS: list[dict] = [
    {
        "sku_id": "P001",
        "product_name": "OPPO Find X9 Ultra",
        "official_status": "launched",
        "pricing": {
            "is_price_public": False,
            "official_price": None,
            "early_bird_deposit": None,
            "deposit_discount_value": None,
            "refund_policy": "Use the live OPPO Austria shop or checkout for current price.",
        },
        "gifts": [],
        "shipping_commitments": {
            "timeline": "Use OPPO Austria official delivery information.",
            "regions": ["AT"],
        },
        "key_features": ["7050mAh battery"],
        "confidential_fields": [],
        "localized_content": {
            "zh": {"key_features": ["7050mAh 电池"]},
            "de": {"key_features": ["7050mAh Akku"]},
            "en": {"key_features": ["7050mAh battery"]},
        },
        "product_url": "https://www.oppo.com/at/",
        "purchase_url": "https://www.oppo.com/at/",
        "is_active": True,
    },
    {
        "sku_id": "P002",
        "product_name": "OPPO Find X9 Pro",
        "official_status": "launched",
        "pricing": {
            "is_price_public": False,
            "official_price": None,
            "early_bird_deposit": None,
            "deposit_discount_value": None,
            "refund_policy": "Use the live OPPO Austria shop or checkout for current price.",
        },
        "gifts": [],
        "shipping_commitments": {
            "timeline": "Use OPPO Austria official delivery information.",
            "regions": ["AT"],
        },
        "key_features": ["7500mAh battery", "80W SUPERVOOC", "50W AIRVOOC"],
        "confidential_fields": [],
        "localized_content": {
            "zh": {"key_features": ["7500mAh 电池", "80W SUPERVOOC 有线快充", "50W AIRVOOC 无线快充"]},
            "de": {"key_features": ["7500mAh Akku", "80W SUPERVOOC", "50W AIRVOOC"]},
            "en": {"key_features": ["7500mAh battery", "80W SUPERVOOC", "50W AIRVOOC"]},
        },
        "product_url": "https://www.oppo.com/at/",
        "purchase_url": "https://www.oppo.com/at/",
        "is_active": True,
    },
    {
        "sku_id": "P003",
        "product_name": "OPPO Find X9",
        "official_status": "launched",
        "pricing": {
            "is_price_public": False,
            "official_price": None,
            "early_bird_deposit": None,
            "deposit_discount_value": None,
            "refund_policy": "Use the live OPPO Austria shop or checkout for current price.",
        },
        "gifts": [],
        "shipping_commitments": {
            "timeline": "Use OPPO Austria official delivery information.",
            "regions": ["AT"],
        },
        "key_features": ["7025mAh battery"],
        "confidential_fields": [],
        "localized_content": {
            "zh": {"key_features": ["7025mAh 电池"]},
            "de": {"key_features": ["7025mAh Akku"]},
            "en": {"key_features": ["7025mAh battery"]},
        },
        "product_url": "https://www.oppo.com/at/",
        "purchase_url": "https://www.oppo.com/at/",
        "is_active": True,
    },
]


class FallbackFactService(FactService):
    @staticmethod
    def _fallback_catalog(launched_only: bool = False) -> list[ProductFactRead]:
        products = [ProductFactRead.model_validate(item) for item in FALLBACK_PRODUCTS]
        if launched_only:
            return [item for item in products if item.official_status.value == "launched"]
        return products

    async def _database_catalog(self, launched_only: bool = False) -> list[ProductFactRead]:
        rows = await super()._database_catalog(launched_only)
        return rows or self._fallback_catalog(launched_only)

    async def list_active(self, launched_only: bool = False) -> list[ProductFactRead]:
        rows = await super().list_active(launched_only)
        return rows or self._fallback_catalog(launched_only)

    async def get(self, sku_id: str) -> ProductFactRead | None:
        item = await super().get(sku_id)
        if item is not None:
            return item
        return next(
            (
                fact
                for fact in self._fallback_catalog(False)
                if fact.sku_id == sku_id or fact.product_name.lower() == sku_id.lower()
            ),
            None,
        )

    async def source_status(self) -> dict:
        status = await super().source_status()
        fallback_count = len(self._fallback_catalog(False))
        status["configured"] = bool(status.get("configured") or fallback_count)
        status["embedded_fallback_product_count"] = fallback_count
        status["embedded_fallback_active"] = not bool(status.get("cached_product_count"))
        return status
