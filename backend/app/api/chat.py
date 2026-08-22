from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.degraded import build_degraded_result, expand_quick_intent
from app.language import detect_language, locale_for, tr
from app.rate_limit import enforce_rate_limit
from app.schemas import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


def sse_event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return int(value) if isinstance(value, int) else None


def _safe_error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        value = error.get("code") or error.get("type")
        return str(value)[:96] if value not in (None, "") else None
    return None


@router.post("/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    await enforce_rate_limit(
        request,
        bucket="chat",
        limit=request.app.state.settings.chat_rate_limit_per_minute,
        window_seconds=60,
    )

    session_id = payload.session_id or str(uuid4())
    payload.session_id = session_id
    language = detect_language(payload.message)
    payload.locale = locale_for(language)
    if payload.context.sku and payload.context.sku.upper().startswith("DEMO-"):
        payload.context.sku = None

    original_message = payload.message
    workflow_payload = payload.model_copy(deep=True)
    workflow_payload.message = expand_quick_intent(original_message)

    async def generate():
        yield sse_event(
            "meta",
            {"session_id": session_id, "language": language},
        )
        try:
            result = await request.app.state.workflow.run(workflow_payload)
            if not str(result.response_markdown or "").strip():
                raise RuntimeError("empty_ai_response")

            for card in result.cards:
                yield sse_event("card", card)
            text = result.response_markdown
            for index in range(0, len(text), 80):
                yield sse_event("message", {"delta": text[index : index + 80]})
                await asyncio.sleep(0)
            yield sse_event(
                "done",
                {"route": result.route, "blocked": result.blocked},
            )
            return
        except Exception as exc:
            request.app.state.audit_service.record(
                "chat_error",
                session_id=session_id,
                request_text=original_message,
                decision="degraded",
                payload={
                    "error_type": exc.__class__.__name__,
                    "http_status": _safe_http_status(exc),
                    "error_code": _safe_error_code(exc),
                },
            )

        try:
            fallback = await build_degraded_result(
                payload,
                language,
                request.app.state.fact_service,
            )
            await request.app.state.conversation_service.save_turn(
                session_id,
                language,
                original_message,
                fallback.response_markdown,
            )
            for card in fallback.cards:
                yield sse_event("card", card)
            text = fallback.response_markdown
            for index in range(0, len(text), 80):
                yield sse_event("message", {"delta": text[index : index + 80]})
                await asyncio.sleep(0)
            yield sse_event(
                "done",
                {"route": "degraded", "blocked": False},
            )
        except Exception as fallback_exc:
            request.app.state.audit_service.record(
                "chat_fallback_error",
                session_id=session_id,
                request_text=original_message,
                decision="failed",
                payload={"error_type": fallback_exc.__class__.__name__},
            )
            yield sse_event(
                "error",
                {
                    "code": "chat_failed",
                    "message": tr(language, "chat_failed"),
                    "error_type": fallback_exc.__class__.__name__,
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
