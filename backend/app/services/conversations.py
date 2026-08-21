from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.cache import HotCache
from app.models import ConversationORM


class ConversationService:
    def __init__(self, session_factory, cache: HotCache, ttl: int, persistence=None):
        self.session_factory = session_factory
        self.cache = cache
        self.ttl = ttl
        self.persistence = persistence

    @staticmethod
    def extract_preferences(message: str, profile: dict) -> dict:
        lower = message.lower()
        updated = dict(profile)

        budget = re.search(
            r"(?:€\s*|max(?:imal)?\s*)(\d{3,4})"
            r"|(?:budget|preis|price)[^\d]{0,12}(\d{3,4})",
            lower,
        )
        if budget:
            updated["budget"] = int(next(group for group in budget.groups() if group))
        if any(term in lower for term in ("camera", "kamera", "拍照", "相机", "portrait", "porträt")):
            updated["camera_priority"] = True
        if any(term in lower for term in ("battery", "akku", "续航", "电池")):
            updated["battery_priority"] = True
        if any(term in lower for term in ("charging", "charge", "laden", "充电", "快充")):
            updated["charging_priority"] = True
        if any(term in lower for term in ("compact", "kompakt", "small", "klein", "小屏")):
            updated["size_preference"] = "compact"
        if any(term in lower for term in ("large", "groß", "gross", "大屏")):
            updated["size_preference"] = "large"
        if any(term in lower for term in ("gaming", "game", "spiel", "游戏")):
            updated["gaming"] = True
        return updated

    def purge_expired(self) -> int:
        if self.persistence and self.persistence.enabled:
            try:
                result = self.persistence.call("conversation_purge", {"ttl_seconds": self.ttl})
                return int(result or 0)
            except Exception:
                pass

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.ttl)
        with self.session_factory() as session:
            result = session.execute(
                delete(ConversationORM).where(ConversationORM.updated_at < cutoff)
            )
            session.commit()
            return int(result.rowcount or 0)

    async def load(self, session_id: str) -> dict:
        cache_key = f"conversation:{session_id}"
        cached = await self.cache.get_json(cache_key)
        if cached:
            return cached

        if self.persistence and self.persistence.enabled:
            try:
                data = await self.persistence.acall(
                    "conversation_get",
                    {"session_id": session_id},
                )
                if data:
                    normalized = {
                        "language": data.get("language") or "de",
                        "profile": data.get("profile") or {},
                        "messages": data.get("messages") or [],
                    }
                    await self.cache.set_json(cache_key, normalized, ttl=self.ttl)
                    return normalized
            except Exception:
                pass

        with self.session_factory() as session:
            row = session.get(ConversationORM, session_id)
            if row is None:
                return {"language": "de", "profile": {}, "messages": []}
            data = {
                "language": row.language,
                "profile": row.profile or {},
                "messages": row.messages or [],
            }
        await self.cache.set_json(cache_key, data, ttl=self.ttl)
        return data

    async def save_turn(
        self,
        session_id: str,
        language: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        data = await self.load(session_id)
        profile = self.extract_preferences(user_message, data.get("profile", {}))
        messages = list(data.get("messages", []))[-16:]
        messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )

        remote_saved = False
        if self.persistence and self.persistence.enabled:
            try:
                await self.persistence.acall(
                    "conversation_upsert",
                    {
                        "session_id": session_id,
                        "language": language,
                        "profile": profile,
                        "messages": messages,
                    },
                )
                remote_saved = True
            except Exception:
                remote_saved = False

        if not remote_saved:
            with self.session_factory() as session:
                row = session.get(ConversationORM, session_id)
                if row is None:
                    row = ConversationORM(session_id=session_id)
                    session.add(row)
                row.language = language
                row.profile = profile
                row.messages = messages
                session.commit()

        await self.cache.set_json(
            f"conversation:{session_id}",
            {"language": language, "profile": profile, "messages": messages},
            ttl=self.ttl,
        )
