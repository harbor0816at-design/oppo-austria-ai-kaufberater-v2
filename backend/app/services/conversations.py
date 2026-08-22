from __future__ import annotations

import json
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
    def _decode_json(value, fallback):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return fallback
        return value

    @classmethod
    def _normalize_profile(cls, value) -> dict:
        value = cls._decode_json(value, {})
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def _normalize_messages(cls, value) -> list[dict]:
        value = cls._decode_json(value, [])
        if not isinstance(value, list):
            return []
        normalized: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            normalized.append({"role": role, "content": content})
        return normalized[-16:]

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
        try:
            with self.session_factory() as session:
                result = session.execute(
                    delete(ConversationORM).where(ConversationORM.updated_at < cutoff)
                )
                session.commit()
                return int(result.rowcount or 0)
        except Exception:
            return 0

    async def load(self, session_id: str) -> dict:
        cache_key = f"conversation:{session_id}"
        try:
            cached = await self.cache.get_json(cache_key)
        except Exception:
            cached = None
        if cached:
            return {
                "language": cached.get("language") or "de",
                "profile": self._normalize_profile(cached.get("profile")),
                "messages": self._normalize_messages(cached.get("messages")),
            }

        if self.persistence and self.persistence.enabled:
            try:
                data = await self.persistence.acall(
                    "conversation_get",
                    {"session_id": session_id},
                )
                if data:
                    normalized = {
                        "language": data.get("language") or "de",
                        "profile": self._normalize_profile(data.get("profile")),
                        "messages": self._normalize_messages(data.get("messages")),
                    }
                    try:
                        await self.cache.set_json(cache_key, normalized, ttl=self.ttl)
                    except Exception:
                        pass
                    return normalized
            except Exception:
                pass

        try:
            with self.session_factory() as session:
                row = session.get(ConversationORM, session_id)
                if row is None:
                    return {"language": "de", "profile": {}, "messages": []}
                data = {
                    "language": row.language or "de",
                    "profile": self._normalize_profile(row.profile),
                    "messages": self._normalize_messages(row.messages),
                }
        except Exception:
            return {"language": "de", "profile": {}, "messages": []}

        try:
            await self.cache.set_json(cache_key, data, ttl=self.ttl)
        except Exception:
            pass
        return data

    async def save_turn(
        self,
        session_id: str,
        language: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        try:
            data = await self.load(session_id)
        except Exception:
            data = {"language": language, "profile": {}, "messages": []}

        profile = self.extract_preferences(
            user_message,
            self._normalize_profile(data.get("profile")),
        )
        messages = self._normalize_messages(data.get("messages"))[-16:]
        messages.extend(
            [
                {"role": "user", "content": str(user_message)},
                {"role": "assistant", "content": str(assistant_message)},
            ]
        )
        messages = messages[-16:]

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
            try:
                with self.session_factory() as session:
                    row = session.get(ConversationORM, session_id)
                    if row is None:
                        row = ConversationORM(session_id=session_id)
                        session.add(row)
                    row.language = language
                    row.profile = profile
                    row.messages = messages
                    session.commit()
            except Exception:
                pass

        try:
            await self.cache.set_json(
                f"conversation:{session_id}",
                {"language": language, "profile": profile, "messages": messages},
                ttl=self.ttl,
            )
        except Exception:
            pass
