from __future__ import annotations

from typing import Any

from app.schemas import ProductFactRead, ProductFactSchema
from app.services.facts import FactService


class PersistentFactService(FactService):
    def __init__(self, *args, persistence: Any | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.persistence = persistence

    async def _database_catalog(self, launched_only: bool = False) -> list[ProductFactRead]:
        if self.persistence and self.persistence.enabled:
            try:
                rows = await self.persistence.acall(
                    "facts_list",
                    {"launched_only": launched_only},
                )
                parsed = [
                    ProductFactRead.model_validate(item)
                    for item in (rows or [])
                ]
                return [
                    item
                    for item in parsed
                    if item.is_active
                    and (not launched_only or item.official_status.value == "launched")
                    and not self._is_internal_demo(item)
                ]
            except Exception:
                pass
        return await super()._database_catalog(launched_only)

    async def _persist_sheet_snapshot(self, products: list[ProductFactSchema]) -> None:
        if self.persistence and self.persistence.enabled:
            try:
                await self.persistence.acall(
                    "facts_replace",
                    {
                        "products": [
                            item.model_dump(mode="json")
                            for item in products
                            if not item.sku_id.upper().startswith("DEMO-")
                        ]
                    },
                    timeout=20.0,
                )
            except Exception:
                pass
        await super()._persist_sheet_snapshot(products)

    async def source_status(self) -> dict:
        status = await super().source_status()
        remote_enabled = bool(self.persistence and self.persistence.enabled)
        persistent_fallback_product_count = 0
        if remote_enabled:
            try:
                persistent_fallback_product_count = len(await self._database_catalog(False))
            except Exception:
                persistent_fallback_product_count = 0
        status["configured"] = bool(status.get("configured") or remote_enabled)
        status["remote_persistence_enabled"] = remote_enabled
        status["persistent_fallback_product_count"] = persistent_fallback_product_count
        return status
