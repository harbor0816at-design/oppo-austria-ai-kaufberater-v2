from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_DOMAIN = b"oppo-kaufberater-persistence-v1\x00"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _private_key(admin_api_key: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(_DOMAIN + admin_api_key.encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_b64(admin_api_key: str) -> str:
    raw = _private_key(admin_api_key).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64url(raw)


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sign_payload(admin_api_key: str, payload: dict[str, Any], timestamp: int | None = None) -> dict[str, str]:
    ts = int(timestamp or time.time())
    body = canonical_json(payload)
    message = str(ts).encode("ascii") + b"." + body
    signature = _private_key(admin_api_key).sign(message)
    return {
        "X-Kaufberater-Timestamp": str(ts),
        "X-Kaufberater-Signature": _b64url(signature),
        "Content-Type": "application/json",
    }
