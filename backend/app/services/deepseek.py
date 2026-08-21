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
        self.oidc_token = os.getenv("VERCEL_OIDC_TOKEN")
        self.use_gateway = not bool(api_key) and bool(self.oidc_token)
        self.model = model
        self.reasoning_model = reasoning_model

        if self.use_gateway:
            self.base_url = "https://ai-gateway.vercel.sh/v1"
            self.api_key = self.oidc_token
        else:
            candidate = base_url.rstrip("/")
            self.base_url = (
                candidate if "deepseek.com" in candidate else "https://api.deepseek.com"
            )
            self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _model_id(self, model: str) -> str:
        if self.use_gateway and not model.startswith("deepseek/"):
            return f"deepseek/{model}"
        return model

    def _payload(self, payload: dict) -> dict:
        prepared = dict(payload)
        prepared["model"] = self._model_id(str(prepared["model"]))
        if self.use_gateway:
            prepared.pop("thinking", None)
        return prepared

    async def health(self) -> dict:
        if not self.api_key:
            return {
                "provider": "deepseek",
                "transport": "not_configured",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
                "authenticated": False,
                "api_reachable": False,
                "response_received": False,
                "error": "DEEPSEEK_AUTH_NOT_CONFIGURED",
            }
        try:
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
                "transport": "vercel_ai_gateway_oidc" if self.use_gateway else "deepseek_direct",
                "model": self._model_id(self.model),
                "reasoning_model": self._model_id(self.reasoning_model),
                "authenticated": True,
                "api_reachable": True,
                "response_received": bool(content),
            }
        except Exception as exc:
            return {
                "provider": "deepseek",
                "transport": "vercel_ai_gateway_oidc" if self.use_gateway else "deepseek_direct",
                "model": self._model_id(self.model),
                "reasoning_model": self._model_id(self.reasoning_model),
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
        if not self.api_key:
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
        return str(data["choices"][0]["message"].get("content") or "").strip()

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        executor: ToolExecutor,
    ) -> str:
        if not self.api_key:
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
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._payload(payload),
            )
            response.raise_for_status()
            return response.json()
