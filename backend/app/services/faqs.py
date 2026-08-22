from __future__ import annotations

import re
import time
from typing import Iterable

from app.language import Language
from app.schemas import FaqItemCreate, FaqItemRead


_TOKEN_RE = re.compile(r"[a-z0-9äöüß]{3,}", re.I)
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\u3400-\u9fffäöüß]+", re.I)


class FaqService:
    def __init__(self, persistence, ttl_seconds: int = 30):
        self.persistence = persistence
        self.ttl_seconds = max(5, ttl_seconds)
        self._cache: list[FaqItemRead] = []
        self._cache_until = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.persistence and self.persistence.enabled)

    @staticmethod
    def _normalize(value: str) -> str:
        value = _PUNCT_RE.sub(" ", str(value or "").lower())
        return _SPACE_RE.sub(" ", value).strip()

    @staticmethod
    def _localized_question(item: FaqItemRead, language: Language) -> str:
        if language == "en" and item.question_en:
            return item.question_en
        if language == "zh" and item.question_zh:
            return item.question_zh
        return item.question_de

    @staticmethod
    def answer_for(item: FaqItemRead, language: Language) -> str:
        if language == "en" and item.answer_en:
            return item.answer_en
        if language == "zh" and item.answer_zh:
            return item.answer_zh
        return item.answer_de

    def invalidate(self) -> None:
        self._cache = []
        self._cache_until = 0.0

    async def list_all(self, active_only: bool = False) -> list[FaqItemRead]:
        if not self.configured:
            return []
        now = time.monotonic()
        if active_only and self._cache and now < self._cache_until:
            return list(self._cache)

        rows = await self.persistence.acall("faq_list", {"active_only": active_only}) or []
        result: list[FaqItemRead] = []
        for row in rows:
            try:
                result.append(FaqItemRead.model_validate(row))
            except Exception:
                continue
        if active_only:
            self._cache = result
            self._cache_until = now + self.ttl_seconds
        return result

    async def create(self, data: FaqItemCreate) -> FaqItemRead:
        row = await self.persistence.acall("faq_create", data.model_dump(mode="json"))
        self.invalidate()
        return FaqItemRead.model_validate(row)

    async def update(self, faq_id: int, data: FaqItemCreate) -> FaqItemRead | None:
        row = await self.persistence.acall(
            "faq_update",
            {"id": faq_id, **data.model_dump(mode="json")},
        )
        self.invalidate()
        return FaqItemRead.model_validate(row) if row else None

    async def delete(self, faq_id: int) -> bool:
        deleted = bool(await self.persistence.acall("faq_delete", {"id": faq_id}))
        self.invalidate()
        return deleted

    @staticmethod
    def _keywords(item: FaqItemRead) -> Iterable[str]:
        for value in item.keywords:
            normalized = FaqService._normalize(value)
            if normalized:
                yield normalized

    async def match(self, message: str, language: Language) -> FaqItemRead | None:
        text = self._normalize(message)
        if not text:
            return None
        items = await self.list_all(active_only=True)
        if not items:
            return None

        message_tokens = set(_TOKEN_RE.findall(text))
        best: tuple[float, FaqItemRead] | None = None
        for item in items:
            question = self._normalize(self._localized_question(item, language))
            score = 0.0
            if question and text == question:
                score += 100
            elif question and len(question) >= 4 and (question in text or text in question):
                score += 8

            for keyword in self._keywords(item):
                if keyword == text:
                    score += 8
                elif keyword in text:
                    score += 4

            question_tokens = set(_TOKEN_RE.findall(question))
            if message_tokens and question_tokens:
                score += 1.5 * len(message_tokens & question_tokens)

            score += max(-1.0, min(2.0, item.priority / 100.0))
            if best is None or score > best[0]:
                best = (score, item)

        return best[1] if best and best[0] >= 4 else None
