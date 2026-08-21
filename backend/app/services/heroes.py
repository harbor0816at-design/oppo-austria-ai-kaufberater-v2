from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.models import HeroSlideORM
from app.schemas import HeroReorderItem, HeroSlideCreate, HeroSlideRead, HeroSlideUpdate


DEFAULT_SLIDES = [
    {
        "id": -1,
        "title": "OPPO Österreich",
        "subtitle": "Offizielle Beratung für dein nächstes Smartphone.",
        "title_en": "OPPO Austria",
        "subtitle_en": "Official guidance for your next smartphone.",
        "title_zh": "OPPO 奥地利",
        "subtitle_zh": "为你的下一部手机提供官方选购建议。",
        "eyebrow": "OPPO KAUFBERATUNG",
        "media_type": "image",
        "media_url": "/assets/hero-brand.svg",
        "mobile_media_url": "/assets/hero-brand.svg",
        "cta_label": "Beratung starten",
        "cta_label_en": "Start consultation",
        "cta_label_zh": "开始咨询",
        "cta_url": "#chat",
        "sort_order": 1,
        "is_active": True,
        "start_at": None,
        "end_at": None,
    },
    {
        "id": -2,
        "title": "Fotografie neu entdecken",
        "subtitle": "Porträt, Reise und Nachtaufnahme — finde das passende OPPO.",
        "title_en": "Rediscover photography",
        "subtitle_en": "Portraits, travel and night shots — find the right OPPO.",
        "title_zh": "重新发现影像乐趣",
        "subtitle_zh": "人像、旅行与夜景——找到更适合你的 OPPO。",
        "eyebrow": "OPPO IMAGING",
        "media_type": "image",
        "media_url": "/assets/hero-camera.svg",
        "mobile_media_url": "/assets/hero-camera.svg",
        "cta_label": "Kamera-Beratung",
        "cta_label_en": "Camera guidance",
        "cta_label_zh": "影像选购建议",
        "cta_url": "#chat",
        "sort_order": 2,
        "is_active": True,
        "start_at": None,
        "end_at": None,
    },
    {
        "id": -3,
        "title": "OPPO in Wien erleben",
        "subtitle": "Persönliche Beratung, Abholung und Datenübertragung im DC Tower.",
        "title_en": "Experience OPPO in Vienna",
        "subtitle_en": "Personal advice, pickup and data transfer at DC Tower.",
        "title_zh": "在维也纳体验 OPPO",
        "subtitle_zh": "在 DC Tower 享受产品咨询、自提与数据迁移服务。",
        "eyebrow": "VIENNA SHOWROOM",
        "media_type": "image",
        "media_url": "/assets/hero-vienna.svg",
        "mobile_media_url": "/assets/hero-vienna.svg",
        "cta_label": "Showroom entdecken",
        "cta_label_en": "Explore the showroom",
        "cta_label_zh": "了解线下展厅",
        "cta_url": "https://www.oppo.com/at/",
        "sort_order": 3,
        "is_active": True,
        "start_at": None,
        "end_at": None,
    },
]


class HeroService:
    def __init__(self, session_factory, persistence=None):
        self.session_factory = session_factory
        self.persistence = persistence

    @staticmethod
    def _read(row: HeroSlideORM) -> HeroSlideRead:
        return HeroSlideRead.model_validate(row)

    def list_all(self) -> list[HeroSlideRead]:
        if self.persistence and self.persistence.enabled:
            rows = self.persistence.call("hero_list", {"active_only": False}) or []
            return [HeroSlideRead.model_validate(row) for row in rows]

        with self.session_factory() as session:
            rows = session.scalars(
                select(HeroSlideORM).order_by(
                    HeroSlideORM.sort_order, HeroSlideORM.id
                )
            ).all()
            return [self._read(row) for row in rows]

    def list_active(self) -> list[HeroSlideRead | dict]:
        if self.persistence and self.persistence.enabled:
            try:
                rows = self.persistence.call("hero_list", {"active_only": True}) or []
                parsed = [HeroSlideRead.model_validate(row) for row in rows]
                return parsed or DEFAULT_SLIDES
            except Exception:
                return DEFAULT_SLIDES

        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            rows = session.scalars(
                select(HeroSlideORM)
                .where(HeroSlideORM.is_active.is_(True))
                .where(or_(HeroSlideORM.start_at.is_(None), HeroSlideORM.start_at <= now))
                .where(or_(HeroSlideORM.end_at.is_(None), HeroSlideORM.end_at >= now))
                .order_by(HeroSlideORM.sort_order, HeroSlideORM.id)
            ).all()
        return [self._read(row) for row in rows] or DEFAULT_SLIDES

    def create(self, data: HeroSlideCreate) -> HeroSlideRead:
        if self.persistence and self.persistence.enabled:
            row = self.persistence.call("hero_create", data.model_dump(mode="json"))
            return HeroSlideRead.model_validate(row)

        with self.session_factory() as session:
            row = HeroSlideORM(**data.model_dump())
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._read(row)

    def update(self, slide_id: int, data: HeroSlideUpdate) -> HeroSlideRead | None:
        if self.persistence and self.persistence.enabled:
            row = self.persistence.call(
                "hero_update",
                {
                    "id": slide_id,
                    "changes": data.model_dump(mode="json", exclude_unset=True),
                },
            )
            return HeroSlideRead.model_validate(row) if row else None

        with self.session_factory() as session:
            row = session.get(HeroSlideORM, slide_id)
            if row is None:
                return None
            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._read(row)

    def delete(self, slide_id: int) -> bool:
        if self.persistence and self.persistence.enabled:
            return bool(self.persistence.call("hero_delete", {"id": slide_id}))

        with self.session_factory() as session:
            row = session.get(HeroSlideORM, slide_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def reorder(self, items: list[HeroReorderItem]) -> list[HeroSlideRead]:
        if self.persistence and self.persistence.enabled:
            rows = self.persistence.call(
                "hero_reorder",
                {"items": [item.model_dump(mode="json") for item in items]},
            ) or []
            return [HeroSlideRead.model_validate(row) for row in rows]

        with self.session_factory() as session:
            for item in items:
                row = session.get(HeroSlideORM, item.id)
                if row is not None:
                    row.sort_order = item.sort_order
            session.commit()
        return self.list_all()
