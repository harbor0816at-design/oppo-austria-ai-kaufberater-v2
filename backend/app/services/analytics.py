from __future__ import annotations

from sqlalchemy import func, select

from app.models import AnalyticsEventORM
from app.schemas import AnalyticsEventCreate


class AnalyticsService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def record(self, data: AnalyticsEventCreate) -> None:
        with self.session_factory() as session:
            session.add(AnalyticsEventORM(**data.model_dump()))
            session.commit()

    def summary(self) -> dict:
        with self.session_factory() as session:
            eligible = session.scalar(
                select(func.count(func.distinct(AnalyticsEventORM.session_id))).where(
                    AnalyticsEventORM.event_name.in_(["assistant_open", "question_sent"])
                )
            ) or 0
            qualified = session.scalar(
                select(func.count(func.distinct(AnalyticsEventORM.session_id))).where(
                    AnalyticsEventORM.event_name.in_(
                        ["launch_subscribe_success", "qualified_private_domain_capture"]
                    )
                )
            ) or 0

            counts = {}
            for name in (
                "assistant_open",
                "question_sent",
                "recommendation_view",
                "comparison_view",
                "whatsapp_click",
                "launch_subscribe_success",
            ):
                counts[name] = session.scalar(
                    select(func.count())
                    .select_from(AnalyticsEventORM)
                    .where(AnalyticsEventORM.event_name == name)
                ) or 0

        return {
            "eligible_sessions": eligible,
            "qualified_private_domain_sessions": qualified,
            "qpcr": round(qualified / eligible, 4) if eligible else 0.0,
            **counts,
        }
