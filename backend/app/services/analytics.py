from __future__ import annotations

from sqlalchemy import func, select

from app.models import AnalyticsEventORM
from app.schemas import AnalyticsEventCreate


class AnalyticsService:
    def __init__(self, session_factory, persistence=None, admin_persistence=None):
        self.session_factory = session_factory
        self.persistence = persistence
        self.admin_persistence = admin_persistence

    def record(self, data: AnalyticsEventCreate) -> None:
        if self.persistence and self.persistence.enabled:
            self.persistence.call("analytics_insert", data.model_dump(mode="json"))
            return

        with self.session_factory() as session:
            session.add(AnalyticsEventORM(**data.model_dump()))
            session.commit()

    def summary(self) -> dict:
        if self.persistence and self.persistence.enabled:
            return self.persistence.call("analytics_summary", {}) or {}

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

    def dashboard(self, days: int = 7) -> dict:
        days = max(1, min(int(days or 7), 90))
        if self.admin_persistence and self.admin_persistence.enabled:
            return self.admin_persistence.call("analytics_dashboard", {"days": days}) or {}

        summary = self.summary()
        visitors = int(summary.get("eligible_sessions") or 0)
        conversions = int(summary.get("qualified_private_domain_sessions") or 0)
        return {
            "days": days,
            "kpis": {
                "visitors": visitors,
                "question_sessions": visitors,
                "questions": int(summary.get("question_sent") or 0),
                "answers": 0,
                "answer_errors": 0,
                "recommendation_views": int(summary.get("recommendation_view") or 0),
                "product_clicks": 0,
                "conversions": conversions,
                "questions_per_visitor": 0,
                "answer_success_pct": 0,
                "qpcr_pct": round((conversions / visitors) * 100, 2) if visitors else 0,
                "product_ctr_pct": 0,
                "avg_latency_ms": None,
                "fast_path_pct": None,
                "backend_errors": 0,
            },
            "daily": [],
            "languages": [],
            "routes": [],
            "quick_replies": [],
            "event_counts": [],
            "recent_errors": [],
        }
