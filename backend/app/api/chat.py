from __future__ import annotations

import asyncio
import json
import re
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.degraded import build_degraded_result, expand_quick_intent
from app.language import detect_language, locale_for, tr
from app.rate_limit import enforce_rate_limit
from app.schemas import AgentResult, ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


_COMPETITOR_ALIASES = {
    "三星": "Samsung",
    "苹果": "Apple iPhone",
    "小米": "Xiaomi",
    "荣耀": "Honor",
    "华为": "Huawei",
    "一加": "OnePlus",
    "谷歌": "Google Pixel",
    "摩托罗拉": "Motorola",
    "索尼": "Sony Xperia",
    "真我": "realme",
}


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


def _normalize_routing_message(message: str) -> str:
    value = str(message or "").strip()
    lower = value.lower()
    aliases: list[str] = []

    x9 = re.search(r"(?<![a-z0-9])x\s*9(?:\s*(pro|ultra))?(?![a-z0-9])", lower, re.I)
    if x9 and "find x9" not in lower:
        suffix = (x9.group(1) or "").strip().title()
        aliases.append(("OPPO Find X9 " + suffix).strip())

    for local_name, canonical in _COMPETITOR_ALIASES.items():
        if local_name in value and canonical.lower() not in lower:
            aliases.append(canonical)

    if not aliases:
        return value
    return value + " (" + "; ".join(dict.fromkeys(aliases)) + ")"


def _is_competitor_comparison(message: str) -> bool:
    return bool(
        re.search(r"\b(?:compare|comparison|versus|vs\.?|vergleich)\b|比较|对比|相比", message, re.I)
        and re.search(
            r"\b(?:samsung|galaxy|apple|iphone|xiaomi|honor|huawei|oneplus|pixel|motorola|sony|realme)\b",
            message,
            re.I,
        )
        and re.search(r"\b(?:oppo|find\s*x9|reno\s*\d+)\b", message, re.I)
    )


def _competitor_unavailable_copy(language: str, oppo_name: str | None = None) -> str:
    name = oppo_name or "OPPO"
    copy = {
        "zh": (
            f"我可以确认 **{name}** 的官方数据，但竞品的最新参数目前无法从实时公开来源可靠核验。"
            "为了避免给你错误信息，我不会编造竞品参数。下面先显示 OPPO 官方信息；你也可以继续问相机、续航、屏幕或性能。"
        ),
        "de": (
            f"Die offiziellen Daten zu **{name}** kann ich bestätigen. Die aktuellsten Daten zum Wettbewerbsmodell "
            "kann ich gerade jedoch nicht zuverlässig aus einer Live-Quelle verifizieren. Deshalb erfinde ich keine Vergleichswerte."
        ),
        "en": (
            f"I can verify the official data for **{name}**, but I cannot currently verify the latest competitor specifications "
            "from a live public source. I will not invent comparison figures."
        ),
    }
    return copy.get(language, copy["de"])


async def _emit_result(result):
    for card in result.cards:
        yield sse_event("card", card)
    text = result.response_markdown
    for index in range(0, len(text), 80):
        yield sse_event("message", {"delta": text[index : index + 80]})
        await asyncio.sleep(0)


async def _save_turn_best_effort(request: Request, session_id: str, language: str, user_message: str, assistant_message: str):
    try:
        await request.app.state.conversation_service.save_turn(
            session_id,
            language,
            user_message,
            assistant_message,
        )
    except Exception as exc:
        request.app.state.audit_service.record(
            "chat_persistence_error",
            session_id=session_id,
            request_text=user_message,
            decision="ignored",
            payload={"error_type": exc.__class__.__name__},
        )


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
    expanded_message = expand_quick_intent(original_message)
    normalized_message = _normalize_routing_message(expanded_message)
    workflow_payload = payload.model_copy(deep=True)
    workflow_payload.message = normalized_message
    is_quick_intent = expanded_message != original_message

    async def generate():
        yield sse_event(
            "meta",
            {"session_id": session_id, "language": language},
        )

        if is_quick_intent:
            try:
                quick_result = await build_degraded_result(
                    payload,
                    language,
                    request.app.state.fact_service,
                )
                async for event in _emit_result(quick_result):
                    yield event
                yield sse_event(
                    "done",
                    {"route": "source_b_fast", "blocked": False, "fast_path": True},
                )
                await _save_turn_best_effort(
                    request,
                    session_id,
                    language,
                    original_message,
                    quick_result.response_markdown,
                )
                request.app.state.audit_service.record(
                    "chat_quick_path",
                    session_id=session_id,
                    request_text=original_message,
                    decision="source_b_fast",
                    payload={"route": quick_result.route},
                )
                return
            except Exception as quick_exc:
                request.app.state.audit_service.record(
                    "chat_quick_path_error",
                    session_id=session_id,
                    request_text=original_message,
                    decision="fallback_to_ai",
                    payload={"error_type": quick_exc.__class__.__name__},
                )

        if _is_competitor_comparison(normalized_message) and not request.app.state.public_search.api_key:
            try:
                grounded = payload.model_copy(deep=True)
                grounded.message = normalized_message
                result = await build_degraded_result(
                    grounded,
                    language,
                    request.app.state.fact_service,
                )
                oppo_name = None
                for card in result.cards:
                    if card.get("type") == "official_fact" and card.get("title"):
                        oppo_name = str(card.get("title"))
                        break
                result = AgentResult(
                    response_markdown=_competitor_unavailable_copy(language, oppo_name),
                    cards=result.cards,
                    route="comparison_unverified",
                    blocked=False,
                )
                async for event in _emit_result(result):
                    yield event
                yield sse_event(
                    "done",
                    {"route": "comparison_unverified", "blocked": False, "fast_path": True},
                )
                await _save_turn_best_effort(
                    request,
                    session_id,
                    language,
                    original_message,
                    result.response_markdown,
                )
                request.app.state.audit_service.record(
                    "chat_competitor_guard",
                    session_id=session_id,
                    request_text=original_message,
                    decision="live_source_unavailable",
                    payload={"normalized": True},
                )
                return
            except Exception as compare_exc:
                request.app.state.audit_service.record(
                    "chat_competitor_guard_error",
                    session_id=session_id,
                    request_text=original_message,
                    decision="fallback_to_ai",
                    payload={"error_type": compare_exc.__class__.__name__},
                )

        try:
            result = await request.app.state.workflow.run(workflow_payload)
            if not str(result.response_markdown or "").strip():
                raise RuntimeError("empty_ai_response")

            async for event in _emit_result(result):
                yield event
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
            async for event in _emit_result(fallback):
                yield event
            yield sse_event(
                "done",
                {"route": "degraded", "blocked": False},
            )
            await _save_turn_best_effort(
                request,
                session_id,
                language,
                original_message,
                fallback.response_markdown,
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
