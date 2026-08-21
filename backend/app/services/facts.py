from __future__ import annotations

from sqlalchemy import select

from app.cache import HotCache
from app.models import AuditLogORM, ProductFactORM
from app.schemas import ProductFactRead, ProductFactSchema


class FactService:
    def __init__(self, session_factory, cache: HotCache):
        self.session_factory = session_factory
        self.cache = cache

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

    async def get(self, sku_id: str) -> ProductFactRead | None:
        if not sku_id or sku_id.upper().startswith("DEMO-"):
            return None
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
        cache_key = f"sku_facts:catalog:{int(launched_only)}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return [ProductFactRead.model_validate(item) for item in cached]

        with self.session_factory() as session:
            stmt = select(ProductFactORM).where(ProductFactORM.is_active.is_(True))
            if launched_only:
                stmt = stmt.where(ProductFactORM.official_status == "launched")
            rows = session.scalars(stmt.order_by(ProductFactORM.product_name.asc())).all()
            result = [
                self._to_schema(row)
                for row in rows
                if not self._is_internal_demo(row)
            ]

        await self.cache.set_json(
            cache_key,
            [item.model_dump(mode="json") for item in result],
            ttl=300,
        )
        return result

    async def upsert(self, fact: ProductFactSchema) -> ProductFactRead:
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

            session.add(
                AuditLogORM(
                    event_type="fact_upsert",
                    sku_id=fact.sku_id,
                    decision="accepted",
                    payload={"official_status": fact.official_status.value},
                )
            )
            session.commit()
            session.refresh(row)
            result = self._to_schema(row)

        await self.cache.set_json(
            f"sku_facts:{fact.sku_id}", result.model_dump(mode="json"), ttl=3600
        )
        await self.cache.delete("sku_facts:catalog:0", "sku_facts:catalog:1")
        return result

    async def delete(self, sku_id: str) -> bool:
        with self.session_factory() as session:
            row = session.get(ProductFactORM, sku_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        await self.cache.delete(
            f"sku_facts:{sku_id}",
            "sku_facts:catalog:0",
            "sku_facts:catalog:1",
        )
        return True
