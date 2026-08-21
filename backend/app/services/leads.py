from __future__ import annotations

from sqlalchemy import select

from app.models import LeadORM
from app.schemas import LeadRead, LeadSubscribeRequest


class LeadService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def subscribe(self, data: LeadSubscribeRequest) -> LeadRead:
        if not data.consent_marketing:
            raise ValueError("Marketing consent is required")
        with self.session_factory() as session:
            row = LeadORM(**data.model_dump())
            session.add(row)
            session.commit()
            session.refresh(row)
            return LeadRead.model_validate(row)

    def list(self, limit: int = 200) -> list[LeadRead]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(LeadORM).order_by(LeadORM.created_at.desc()).limit(limit)
            ).all()
            return [LeadRead.model_validate(row) for row in rows]
