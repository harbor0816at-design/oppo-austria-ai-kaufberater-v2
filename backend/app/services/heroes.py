from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select

from app.models import HeroSlideORM
from app.schemas import HeroReorderItem, HeroSlideCreate, HeroSlideRead, HeroSlideUpdate


logger = logging.getLogger(__name__)
_DEFAULT_SLIDES_PATH = Path(__file__).resolve().parents[2] / "data" / "default_hero_slides.json"


def _load_default_slides() -> list[dict]:
    try:
        with _DEFAULT_SLIDES_PATH.open(encoding="utf-8") as source:
            slides = json.load(source)
        if not isinstance(slides, list) or not slides:
            raise ValueError("default hero slide file must contain a non-empty JSON list")
        return slides
    except Exception:
        logger.exception("hero_slides_fallback_load_failed")
        return []


DEFAULT_SLIDES = _load_default_slides()


class HeroService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    @staticmethod
    def _read(row: HeroSlideORM) -> HeroSlideRead:
        return HeroSlideRead.model_validate(row)

    def list_all(self) -> list[HeroSlideRead]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(HeroSlideORM).order_by(
                    HeroSlideORM.sort_order, HeroSlideORM.id
                )
            ).all()
            return [self._read(row) for row in rows]

    def list_active(self) -> list[HeroSlideRead | dict]:
        now = datetime.now(timezone.utc)
        try:
            with self.session_factory() as session:
                rows = session.scalars(
                    select(HeroSlideORM)
                    .where(HeroSlideORM.is_active.is_(True))
                    .where(or_(HeroSlideORM.start_at.is_(None), HeroSlideORM.start_at <= now))
                    .where(or_(HeroSlideORM.end_at.is_(None), HeroSlideORM.end_at >= now))
                    .order_by(HeroSlideORM.sort_order, HeroSlideORM.id)
                ).all()
            return [self._read(row) for row in rows] or list(DEFAULT_SLIDES)
        except Exception:
            logger.exception("hero_slides_database_read_failed")
            return list(DEFAULT_SLIDES)

    def create(self, data: HeroSlideCreate) -> HeroSlideRead:
        with self.session_factory() as session:
            row = HeroSlideORM(**data.model_dump())
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._read(row)

    def update(self, slide_id: int, data: HeroSlideUpdate) -> HeroSlideRead | None:
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
        with self.session_factory() as session:
            row = session.get(HeroSlideORM, slide_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def reorder(self, items: list[HeroReorderItem]) -> list[HeroSlideRead]:
        with self.session_factory() as session:
            for item in items:
                row = session.get(HeroSlideORM, item.id)
                if row is not None:
                    row.sort_order = item.sort_order
            session.commit()
        return self.list_all()
