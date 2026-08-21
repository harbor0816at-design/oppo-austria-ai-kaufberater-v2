from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.language import detect_language, locale_for, tr
from app.rate_limit import enforce_rate_limit
from app.schemas import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


def sse_event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    async def generate():
        try:
            yield sse_event(
                "meta",
                {"session_id": session_id, "language": language},
            )
            result = await request.app.state.workflow.run(payload)
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
        except Exception as exc:
            request.app.state.audit_service.record(
                "chat_error",
                session_id=session_id,
                request_text=payload.message,
                decision="failed",
                payload={"error_type": exc.__class__.__name__},
            )
            yield sse_event(
                "error",
                {
                    "code": "chat_failed",
                    "message": tr(language, "chat_failed"),
                    "error_type": exc.__class__.__name__,
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
