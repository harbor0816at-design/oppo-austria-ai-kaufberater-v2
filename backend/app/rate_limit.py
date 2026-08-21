from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request, status


def _client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        raw = forwarded.split(",", 1)[0].strip()
    else:
        raw = request.headers.get("x-real-ip", "").strip()
    if not raw and request.client is not None:
        raw = request.client.host or "unknown"
    if not raw:
        raw = "unknown"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


async def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    if limit <= 0:
        return
    key = f"rate_limit:{bucket}:{_client_identity(request)}"
    count = await request.app.state.cache.increment(key, ttl=window_seconds)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(window_seconds)},
        )
