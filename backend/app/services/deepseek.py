from __future__ import annotations

import json
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
        self.api_key = api_key
        self.model = model
        self.reasoning_model = reasoning_model
        candidate = base_url.rstrip("/")
        self.base_url = (
            candidate if "deepseek.com" in candidate else "https://api.deepseek.com"
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def health(self) -> dict:
        if not self.api_key:
            return {
                "provider": "deepseek",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
                "authenticated": False,
                "api_reachable": False,
                "response_received": False,
                "error": "DEEPSEEK_API_KEY_NOT_CONFIGURED",
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
                timeout=15,
            )
            content = str(result["choices"][0]["message"].get("content", "")).strip()
            return {
                "provider": "deepseek",
                "model": self.model,
                "reasoning_model": self.reasoning_model,
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
                json=payload,
            )
            response.raise_for_status()
            return response.json()
