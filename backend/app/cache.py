from __future__ import annotations

import json
import time
from typing import Any

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None


class HotCache:
    def __init__(self, redis_url: str | None = None):
        self.memory: dict[str, tuple[float | None, Any]] = {}
        self.redis = None
        if redis_url and Redis is not None:
            self.redis = Redis.from_url(redis_url, decode_responses=True)

    async def ping(self) -> bool:
        if self.redis is None:
            return False
        try:
            return bool(await self.redis.ping())
        except Exception:
            self.redis = None
            return False

    async def get_json(self, key: str):
        if self.redis is not None:
            try:
                raw = await self.redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                self.redis = None

        item = self.memory.get(key)
        if not item:
            return None
        expires, value = item
        if expires is not None and expires < time.time():
            self.memory.pop(key, None)
            return None
        return value

    async def set_json(self, key: str, value: Any, ttl: int | None = None):
        if self.redis is not None:
            try:
                await self.redis.set(
                    key,
                    json.dumps(value, ensure_ascii=False),
                    ex=ttl,
                )
                return
            except Exception:
                self.redis = None
        expires = time.time() + ttl if ttl else None
        self.memory[key] = (expires, value)

    async def delete(self, *keys: str):
        if self.redis is not None:
            try:
                await self.redis.delete(*keys)
            except Exception:
                self.redis = None
        for key in keys:
            self.memory.pop(key, None)

    async def close(self):
        if self.redis is not None:
            await self.redis.aclose()
