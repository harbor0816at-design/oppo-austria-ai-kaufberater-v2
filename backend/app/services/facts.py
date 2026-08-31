from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.cache import HotCache
from app.models import AuditLogORM, ProductFactORM
from app.schemas import ProductFactRead, ProductFactSchema
from app.services.google_sheets import GoogleSheetsSource


class FactService:
    def __init__(
        self,
        session_factory,
        cache: HotCache,
        *,
        source_b_provider: str = "database",
        google_source: GoogleSheetsSource | None = None,
        sheet_cache_ttl_seconds: int = 300,
        fail_open: bool = True,
    ):
        self.session_factory = session_factory
        self.cache = cache
        self.source_b_provider = source_b_provider.strip().lower()
        self.google_source = google_source
        self.sheet_cache_ttl_seconds = sheet_cache_ttl_seconds
        self.fail_open = fail_open
        self.last_sync_at: str | None = None
        self.last_sync_count = 0
        self.last_sync_errors: list[str] = []
        self.last_service_count = 0
        self.last_knowledge_count = 0
        self.last_competitor_fact_count = 0

    @staticmethod
    def _to_schema(row: ProductFactORM) -> ProductFactRead:
        return ProductFactRead(
            sku_id=row.sku_id,
            product_name=row.product_name,
            official_status=row.official_status,
            pricing=row.pricing,
            gifts=row.gifts or [],
            shipping_commitments=row.shipping_commitments,
            key_features=row.key_features or [],
            confidential_fields=row.confidential_fields or [],
            localized_content=row.localized_content or {},
            product_url=row.product_url,
            purchase_url=row.purchase_url,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _is_internal_demo(row: ProductFactORM | ProductFactRead) -> bool:
        return (
            row.sku_id.upper().startswith("DEMO-")
            or "demo device" in row.product_name.lower()
            or "interner test" in row.product_name.lower()
            or "internal test" in row.product_name.lower()
        )

    async def _database_catalog(self, launched_only: bool = False) -> list[ProductFactRead]:
        with self.session_factory() as session:
            stmt = select(ProductFactORM).where(ProductFactORM.is_active.is_(True))
            if launched_only:
                stmt = stmt.where(ProductFactORM.official_status == "launched")
            rows = session.scalars(stmt.order_by(ProductFactORM.product_name.asc())).all()
            return [self._to_schema(row) for row in rows if not self._is_internal_demo(row)]

    async def _persist_sheet_snapshot(self, products: list[ProductFactSchema]) -> None:
        active_skus = {item.sku_id for item in products}
        with self.session_factory() as session:
            existing = session.scalars(select(ProductFactORM)).all()
            for row in existing:
                if not row.sku_id.upper().startswith("DEMO-") and row.sku_id not in active_skus:
                    row.is_active = False

            for fact in products:
                payload = fact.model_dump(mode="json")
                row = session.get(ProductFactORM, fact.sku_id)
                if row is None:
                    row = ProductFactORM(sku_id=fact.sku_id)
                    session.add(row)
                for field in (
                    "product_name",
                    "official_status",
                    "pricing",
                    "gifts",
                    "shipping_commitments",
                    "key_features",
                    "confidential_fields",
                    "localized_content",
                    "product_url",
                    "purchase_url",
                    "is_active",
                ):
                    setattr(row, field, payload[field])

            session.add(
                AuditLogORM(
                    event_type="source_b_google_sheet_sync",
                    decision="accepted",
                    payload={
                        "product_count": len(products),
                        "spreadsheet_id": (
                            self.google_source.spreadsheet_id if self.google_source else None
                        ),
                    },
                )
            )
            session.commit()

    async def _sheet_catalog(self, *, force: bool = False) -> list[ProductFactRead]:
        cache_key = "source_b:google_sheets:catalog"
        if not force:
            cached = await self.cache.get_json(cache_key)
            if cached:
                return [ProductFactRead.model_validate(item) for item in cached]

        if self.google_source is None or not self.google_source.configured:
            raise RuntimeError("Google Sheets Source_B is not configured")

        result = await asyncio.to_thread(self.google_source.load)
        self.last_sync_at = result.fetched_at
        self.last_sync_count = len(result.products)
        self.last_sync_errors = result.errors
        self.last_service_count = len(result.services)
        self.last_knowledge_count = len(result.knowledge)
        self.last_competitor_fact_count = len(result.competitor_facts)
        if result.errors and not result.products:
            raise RuntimeError("Google Sheets Source_B contains no valid products")

        await self.cache.set_json(
            "source_b:google_sheets:context",
            {
                "services": result.services,
                "knowledge": result.knowledge,
                "promotions": result.promotions,
                "competitor_references": result.competitor_references,
                "competitor_facts": result.competitor_facts,
                "fetched_at": result.fetched_at,
            },
            ttl=self.sheet_cache_ttl_seconds,
        )
        await self._persist_sheet_snapshot(result.products)
        parsed = [ProductFactRead.model_validate(item.model_dump()) for item in result.products]
        await self.cache.set_json(
            cache_key,
            [item.model_dump(mode="json") for item in parsed],
            ttl=self.sheet_cache_ttl_seconds,
        )
        await self.cache.delete("sku_facts:catalog:0", "sku_facts:catalog:1")
        return parsed

    async def refresh_source(self) -> dict:
        if self.source_b_provider != "google_sheets":
            catalog = await self._database_catalog(False)
            return {"provider": "database", "product_count": len(catalog)}
        catalog = await self._sheet_catalog(force=True)
        return {
            "provider": "google_sheets",
            "spreadsheet_id": self.google_source.spreadsheet_id if self.google_source else None,
            "product_count": len(catalog),
            "errors": self.last_sync_errors,
            "synced_at": self.last_sync_at,
        }

    async def source_status(self) -> dict:
        cached = await self.cache.get_json("source_b:google_sheets:catalog")
        return {
            "provider": self.source_b_provider,
            "spreadsheet_id": self.google_source.spreadsheet_id if self.google_source else None,
            "configured": bool(self.google_source and self.google_source.configured),
            "service_account_email": self.google_source.client_email if self.google_source else None,
            "credential": (
                self.google_source.credential_status
                if self.google_source
                else {
                    "json_present": False,
                    "base64_present": False,
                    "selected_source": None,
                    "parsed": False,
                    "error": "source_not_initialized",
                }
            ),
            "cache_ttl_seconds": self.sheet_cache_ttl_seconds,
            "cached_product_count": len(cached or []),
            "last_sync_at": self.last_sync_at,
            "last_sync_count": self.last_sync_count,
            "last_sync_errors": self.last_sync_errors,
            "last_service_count": self.last_service_count,
            "last_knowledge_count": self.last_knowledge_count,
            "last_competitor_fact_count": self.last_competitor_fact_count,
        }

    async def source_context(self, language: str = "de") -> dict:
        """Return localized non-product Source_B facts and hard answer policies."""
        if self.source_b_provider != "google_sheets":
            return {"policies": [], "services": [], "faqs": [], "promotions": []}

        context = await self.cache.get_json("source_b:google_sheets:context")
        if not context:
            try:
                await self._sheet_catalog(force=True)
            except Exception:
                if not self.fail_open:
                    raise
            context = await self.cache.get_json("source_b:google_sheets:context") or {}

        lang = language if language in {"de", "en", "zh"} else "de"
        policies, faqs = [], []
        for row in context.get("knowledge", []):
            category = str(row.get("category", "")).strip()
            item = {
                "id": str(row.get("faq_id", "")).strip(),
                "category": category,
                "question": str(row.get(f"question_{lang}", "")).strip(),
                "answer": str(row.get(f"answer_{lang}", "")).strip(),
                "market": str(row.get("market", "AT")).strip(),
                "source_url": str(row.get("source_url", "")).strip() or None,
                "verified_at": str(row.get("verified_at", "")).strip() or None,
                "notes": str(row.get("notes", "")).strip() or None,
            }
            (policies if category == "system_policy" else faqs).append(item)

        services = []
        for row in context.get("services", []):
            services.append({
                "service_key": str(row.get("service_key", "")).strip(),
                "market": str(row.get("market", "AT")).strip(),
                "title": str(row.get(f"title_{lang}", "")).strip(),
                "body": str(row.get(f"body_{lang}", "")).strip(),
                "source_url": str(row.get("source_url", "")).strip() or None,
                "updated_at": str(row.get("updated_at", "")).strip() or None,
            })

        return {
            "policies": policies,
            "services": services,
            "faqs": faqs,
            "promotions": context.get("promotions", []),
            "competitor_references": context.get("competitor_references", []),
            "competitor_facts": context.get("competitor_facts", []),
            "fetched_at": context.get("fetched_at"),
        }

    async def get(self, sku_id: str) -> ProductFactRead | None:
        if not sku_id or sku_id.upper().startswith("DEMO-"):
            return None
        if self.source_b_provider == "google_sheets":
            try:
                catalog = await self._sheet_catalog()
                return next((item for item in catalog if item.sku_id == sku_id), None)
            except Exception:
                if not self.fail_open:
                    raise

        cache_key = f"sku_facts:{sku_id}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return ProductFactRead.model_validate(cached)
        with self.session_factory() as session:
            row = session.get(ProductFactORM, sku_id)
            if row is None or self._is_internal_demo(row):
                return None
            schema = self._to_schema(row)
        await self.cache.set_json(cache_key, schema.model_dump(mode="json"), ttl=3600)
        return schema

    async def list_active(self, launched_only: bool = False) -> list[ProductFactRead]:
        if self.source_b_provider == "google_sheets":
            try:
                catalog = await self._sheet_catalog()
                return [
                    item
                    for item in catalog
                    if item.is_active
                    and (not launched_only or item.official_status.value == "launched")
                    and not self._is_internal_demo(item)
                ]
            except Exception:
                if not self.fail_open:
                    raise
        return await self._database_catalog(launched_only)

    async def upsert(self, fact: ProductFactSchema) -> ProductFactRead:
        if self.source_b_provider == "google_sheets":
            raise ValueError(
                "Manual Source_B writes are disabled. Edit the Google Sheet instead."
            )
        if fact.sku_id.upper().startswith("DEMO-"):
            raise ValueError("DEMO-* SKUs are not accepted in the production fact store")
        payload = fact.model_dump(mode="json")
        with self.session_factory() as session:
            row = session.get(ProductFactORM, fact.sku_id)
            if row is None:
                row = ProductFactORM(sku_id=fact.sku_id)
                session.add(row)
            for field in (
                "product_name",
                "official_status",
                "pricing",
                "gifts",
                "shipping_commitments",
                "key_features",
                "confidential_fields",
                "localized_content",
                "product_url",
                "purchase_url",
                "is_active",
            ):
                setattr(row, field, payload[field])
            session.commit()
            session.refresh(row)
            result = self._to_schema(row)
        await self.cache.delete("sku_facts:catalog:0", "sku_facts:catalog:1")
        return result

    async def delete(self, sku_id: str) -> bool:
        if self.source_b_provider == "google_sheets":
            raise ValueError(
                "Manual Source_B deletes are disabled. Set is_active=FALSE in the Google Sheet."
            )
        with self.session_factory() as session:
            row = session.get(ProductFactORM, sku_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        await self.cache.delete(
            f"sku_facts:{sku_id}", "sku_facts:catalog:0", "sku_facts:catalog:1"
        )
        return True
