from __future__ import annotations

from app.models import AuditLogORM


class AuditService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def record(
        self,
        event_type: str,
        *,
        session_id: str | None = None,
        sku_id: str | None = None,
        request_text: str | None = None,
        decision: str | None = None,
        payload: dict | None = None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                AuditLogORM(
                    event_type=event_type,
                    session_id=session_id,
                    sku_id=sku_id,
                    request_text=request_text,
                    decision=decision,
                    payload=payload or {},
                )
            )
            session.commit()
