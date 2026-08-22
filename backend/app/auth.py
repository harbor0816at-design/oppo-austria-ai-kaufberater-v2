from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status

from app.rate_limit import enforce_rate_limit
from app.services.persistence import RemotePersistenceClient


def _function_url(persistence_url: str | None, slug: str) -> str | None:
    value = (persistence_url or "").strip().rstrip("/")
    if not value or "/" not in value:
        return None
    return value.rsplit("/", 1)[0] + f"/{slug}"


def _invalid_admin_key() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin key",
    )


async def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> None:
    # Admin login is deliberately stricter than the public chat rate limit.
    # This protects human-memorable operations credentials from brute-force attempts.
    await enforce_rate_limit(
        request,
        bucket="admin-auth",
        limit=10,
        window_seconds=60,
    )

    settings = request.app.state.settings
    if settings.is_production and not settings.admin_key_secure:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured",
        )
    if not x_admin_key:
        raise _invalid_admin_key()

    # Production admin login is intentionally decoupled from ADMIN_API_KEY.
    # ADMIN_API_KEY remains an internal Ed25519 persistence-signing root only.
    # The human admin credential is verified against a PBKDF2 verifier stored in
    # the private Supabase runtime_config table through a signed internal request.
    auth_client = RemotePersistenceClient(
        _function_url(settings.persistence_url, "kaufberater-admin-auth"),
        settings.admin_api_key,
        settings.remote_persistence_enabled,
    )

    if settings.is_production:
        if not auth_client.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin authentication service is not configured",
            )
        try:
            result = await auth_client.acall(
                "admin_verify",
                {"key": x_admin_key},
                timeout=5.0,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin authentication service is unavailable",
            ) from exc

        if not result or not result.get("configured"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin login credential is not configured",
            )
        if not result.get("valid"):
            raise _invalid_admin_key()
        return

    # Local development keeps the legacy environment-key fallback so developers
    # can run the backend without the remote private auth service.
    if auth_client.enabled:
        try:
            result = await auth_client.acall(
                "admin_verify",
                {"key": x_admin_key},
                timeout=5.0,
            )
            if result and result.get("configured"):
                if result.get("valid"):
                    return
                raise _invalid_admin_key()
        except HTTPException:
            raise
        except Exception:
            pass

    if not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise _invalid_admin_key()
