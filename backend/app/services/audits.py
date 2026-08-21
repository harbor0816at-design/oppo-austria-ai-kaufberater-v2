from __future__ import annotations

import hashlib

from app.models import AuditLogORM


class AuditService:
    def __init__(self, session_factory, persistence=None):
        self.session_factory = session_factory
        self.persistence = persistence

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
        safe_payload = dict(payload or {})
        if request_text:
            safe_payload.setdefault(
                "request_sha256",
                hashlib.sha256(request_text.encode("utf-8")).hexdigest(),
            )
            safe_payload.setdefault("request_length", len(request_text))

        record = {
            "event_type": event_type,
            "session_id": session_id,
            "sku_id": sku_id,
            "request_text": None,
            "decision": decision,
            "payload": safe_payload,
        }
        if self.persistence and self.persistence.enabled:
            try:
                self.persistence.call("audit_insert", record)
                return
            except Exception:
                # Audit persistence must never break the consumer chat path.
                pass

        with self.session_factory() as session:
            session.add(AuditLogORM(**record))
            session.commit()
