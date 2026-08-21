import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.persistence_auth import canonical_json, public_key_b64, sign_payload


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_persistence_signature_verifies_with_public_key():
    key = "this-is-a-production-grade-admin-key"
    payload = {"op": "health", "nested": {"b": 2, "a": 1}}
    headers = sign_payload(
        key,
        payload,
        timestamp=1700000000,
        nonce="fixed-test-nonce",
    )
    public_key = Ed25519PublicKey.from_public_bytes(_decode(public_key_b64(key)))
    message = b"1700000000.fixed-test-nonce." + canonical_json(payload)
    public_key.verify(_decode(headers["X-Kaufberater-Signature"]), message)
    assert headers["X-Kaufberater-Nonce"] == "fixed-test-nonce"


def test_persistence_public_key_is_stable():
    key = "this-is-a-production-grade-admin-key"
    assert public_key_b64(key) == public_key_b64(key)
    assert public_key_b64(key) != public_key_b64(key + "-different")
