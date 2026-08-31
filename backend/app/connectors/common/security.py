import hashlib
import hmac
import time


def hash_link_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    payload = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    *, secret: str, timestamp: str, body: bytes, signature: str, now: int | None = None, tolerance_seconds: int = 300
) -> bool:
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - sent_at) > tolerance_seconds:
        return False
    expected = sign_webhook(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)
