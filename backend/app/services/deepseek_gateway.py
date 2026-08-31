from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable

import httpx

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
GATEWAY_FALLBACK_MODELS = [
    "deepseek-v4-flash-0731",
    "deepseek-v4-pro-0813",
    "deepseek-v3.2",
]


class ProductionDeepSeekClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        reasoning_model: str,
        base_url: str,
    ):
        self.api_key = (api_key or "").strip() or None
        self.model = model
        self.reasoning_model = reasoning_model
        candidate = base_url.rstrip("/")
        self.base_url = (
            candidate if "deepseek.com" in candidate else "https://api.deepseek.com"
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.api_key
            or os.getenv("VERCEL_OIDC_TOKEN")
            or os.getenv("VERCEL")
            or os.getenv("VERCEL_ENV")
        )

    async def health(self) -> dict:
        if not self.configured:
            return {
                "provider": "deepseek",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
                "authenticated": False,
                "api_reachable": False,
                "response_received": False,
                "error": "DEEPSEEK_API_KEY_OR_VERCEL_OIDC_NOT_CONFIGURED",
            }
        try:
            data = await self._request(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Reply only with OK"}],
                    "max_tokens": 8,
                    "temperature": 0,
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
                timeout=15,
            )
            content = self._final_content(data)
            return {
                "provider": "deepseek",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
                "transport": data.get("_transport", "direct"),
                "model_used": data.get("_model_used"),
                "authenticated": True,
                "api_reachable": True,
                "response_received": bool(content),
            }
        except Exception as exc:
            return {
                "provider": "deepseek",
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
        if not self.configured:
            raise RuntimeError("DeepSeek is not configured")
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
        return self._final_content(data)

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        executor: ToolExecutor,
    ) -> str:
        if not self.configured:
            raise RuntimeError("DeepSeek is not configured")

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
                return self._message_content(message)

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

    async def _resolve_auth(self) -> tuple[str, str, str]:
        if self.api_key:
            return self.api_key, self.base_url, "direct"

        token = os.getenv("VERCEL_OIDC_TOKEN")
        if not token:
            try:
                from vercel.oidc.aio import get_vercel_oidc_token

                token = await get_vercel_oidc_token()
            except Exception:
                token = None
        if not token:
            raise RuntimeError("Vercel OIDC token is not available")
        return token, GATEWAY_BASE_URL, "vercel_ai_gateway_oidc"

    @staticmethod
    def _gateway_model(model: str) -> str:
        return model if "/" in model else f"deepseek/{model}"

    @staticmethod
    def _message_content(message: dict[str, Any]) -> str:
        content = message.get("content") or ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif item:
                    parts.append(str(item))
            return "".join(parts).strip()
        return str(content).strip()

    @classmethod
    def _final_content(cls, data: dict[str, Any]) -> str:
        return cls._message_content(data["choices"][0]["message"])

    def _payload_for_transport(
        self,
        payload: dict[str, Any],
        *,
        transport: str,
        model: str,
    ) -> dict[str, Any]:
        prepared = dict(payload)
        if transport == "vercel_ai_gateway_oidc":
            prepared["model"] = self._gateway_model(model)
            if "thinking" in prepared:
                prepared.pop("thinking", None)
                prepared["reasoning"] = {"effort": "none"}
        else:
            prepared["model"] = model
        return prepared

    async def _request(self, payload: dict[str, Any], timeout: float = 45):
        token, base_url, transport = await self._resolve_auth()
        primary_model = str(payload.get("model") or self.model)
        fallback_models = [primary_model]
        if transport == "vercel_ai_gateway_oidc":
            for model in GATEWAY_FALLBACK_MODELS:
                if model not in fallback_models:
                    fallback_models.append(model)

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for model in fallback_models:
                prepared = self._payload_for_transport(
                    payload,
                    transport=transport,
                    model=model,
                )
                try:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json=prepared,
                    )
                    response.raise_for_status()
                    data = response.json()
                    data["_transport"] = transport
                    data["_model_used"] = prepared.get("model")
                    return data
                except Exception as exc:
                    last_error = exc
                    if transport != "vercel_ai_gateway_oidc":
                        break
                    await asyncio.sleep(0.15)

        if last_error is not None:
            raise last_error
        raise RuntimeError("DeepSeek request failed")
