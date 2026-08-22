from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

import httpx

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        reasoning_model: str,
        base_url: str,
    ):
        self.direct_api_key = api_key
        self.model = model
        self.reasoning_model = reasoning_model
        candidate = base_url.rstrip("/")
        self.direct_base_url = (
            candidate if "deepseek.com" in candidate else "https://api.deepseek.com"
        )
        self.gateway_base_url = "https://ai-gateway.vercel.sh/v1"

    @property
    def configured(self) -> bool:
        # Direct BYOK works everywhere. On Vercel, the OIDC helper resolves the
        # short-lived project token from the current request context.
        return bool(
            self.direct_api_key
            or os.getenv("VERCEL_OIDC_TOKEN")
            or os.getenv("VERCEL")
            or os.getenv("VERCEL_ENV")
        )

    async def _resolve_auth(self) -> tuple[str, str, bool]:
        if self.direct_api_key:
            return self.direct_api_key, self.direct_base_url, False

        token = os.getenv("VERCEL_OIDC_TOKEN")
        if not token:
            try:
                from vercel.oidc.aio import get_vercel_oidc_token

                token = await get_vercel_oidc_token()
            except Exception:
                token = None

        if token:
            return token, self.gateway_base_url, True
        raise RuntimeError("DeepSeek authentication is not configured")

    @staticmethod
    def _model_id(model: str, use_gateway: bool) -> str:
        if use_gateway and not model.startswith("deepseek/"):
            return f"deepseek/{model}"
        return model

    @classmethod
    def _payload(cls, payload: dict, use_gateway: bool) -> dict:
        prepared = dict(payload)
        prepared["model"] = cls._model_id(str(prepared["model"]), use_gateway)
        if use_gateway:
            # DeepSeek-native `thinking` is not part of the OpenAI-compatible
            # AI Gateway contract used here.
            prepared.pop("thinking", None)
        return prepared

    async def health(self) -> dict:
        try:
            _token, _base_url, use_gateway = await self._resolve_auth()
            result = await self._request(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Reply only with OK"}],
                    "max_tokens": 8,
                    "temperature": 0,
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
                timeout=20,
            )
            content = str(result["choices"][0]["message"].get("content", "")).strip()
            return {
                "provider": "deepseek",
                "transport": "vercel_ai_gateway_oidc" if use_gateway else "deepseek_direct",
                "model": self._model_id(self.model, use_gateway),
                "reasoning_model": self._model_id(self.reasoning_model, use_gateway),
                "authenticated": True,
                "api_reachable": True,
                "response_received": bool(content),
            }
        except Exception as exc:
            return {
                "provider": "deepseek",
                "transport": "unavailable",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
                "authenticated": False,
                "api_reachable": False,
                "response_received": False,
                "error": exc.__class__.__name__,
            }

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1400,
        temperature: float = 0.2,
    ) -> str:
        data = await self._request(
            {
                "model": self.model,
                "messages": messages,
                "thinking": {"type": "disabled"},
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
        )
        return str(data["choices"][0]["message"].get("content") or "").strip()

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        executor: ToolExecutor,
    ) -> str:
        history = list(messages)
        for _ in range(3):
            payload = {
                "model": self.model,
                "messages": history,
                "tools": tools,
                "tool_choice": "auto",
                "thinking": {"type": "disabled"},
                "temperature": 0.2,
                "max_tokens": 1400,
                "stream": False,
            }
            data = await self._request(payload)
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return str(message.get("content") or "").strip()

            history.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                result = await executor(name, arguments)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        raise RuntimeError("DeepSeek tool loop exceeded the maximum number of rounds")

    async def _request(self, payload: dict, timeout: float = 45):
        token, base_url, use_gateway = await self._resolve_auth()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=self._payload(payload, use_gateway),
            )
            response.raise_for_status()
            return response.json()
