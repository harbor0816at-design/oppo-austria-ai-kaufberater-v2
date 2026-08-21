from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> None:
    settings = request.app.state.settings
    if settings.is_production and not settings.admin_key_secure:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured",
        )

    expected = settings.admin_api_key
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )
