from __future__ import annotations

from typing import Any

import httpx

from app.persistence_auth import canonical_json, sign_payload


class RemotePersistenceClient:
    def __init__(self, url: str | None, admin_api_key: str, enabled: bool):
        self.url = (url or "").strip()
        self.admin_api_key = admin_api_key
        self.enabled = bool(enabled and self.url and admin_api_key)

    def _request_parts(self, operation: str, data: dict[str, Any] | None = None):
        payload = {"op": operation, "data": data or {}}
        content = canonical_json(payload)
        headers = sign_payload(self.admin_api_key, payload)
        return content, headers

    def call(self, operation: str, data: dict[str, Any] | None = None, timeout: float = 12.0):
        if not self.enabled:
            raise RuntimeError("Remote persistence is not configured")
        content, headers = self._request_parts(operation, data)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(self.url, content=content, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(payload.get("error") or "Remote persistence failed")
        return payload.get("data")

    async def acall(self, operation: str, data: dict[str, Any] | None = None, timeout: float = 12.0):
        if not self.enabled:
            raise RuntimeError("Remote persistence is not configured")
        content, headers = self._request_parts(operation, data)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.url, content=content, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(payload.get("error") or "Remote persistence failed")
        return payload.get("data")

    def health(self) -> bool:
        if not self.enabled:
            return False
        try:
            result = self.call("health", timeout=5.0)
            return bool(result and result.get("status") == "ok")
        except Exception:
            return False

    async def ahealth(self) -> bool:
        if not self.enabled:
            return False
        try:
            result = await self.acall("health", timeout=5.0)
            return bool(result and result.get("status") == "ok")
        except Exception:
            return False
