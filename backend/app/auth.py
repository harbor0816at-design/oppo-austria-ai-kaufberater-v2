from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> None:
    expected = request.app.state.settings.admin_api_key
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )
