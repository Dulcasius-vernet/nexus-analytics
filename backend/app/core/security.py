"""Password hashing and signed, expiring browser sessions (stdlib only)."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings

PBKDF2_ROUNDS = 310_000
SESSION_SECONDS = 12 * 60 * 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def create_session(user_id: int, business_id: int) -> str:
    now = int(time.time())
    payload = _b64(json.dumps({"uid": user_id, "bid": business_id, "iat": now, "exp": now + SESSION_SECONDS}, separators=(",", ":")).encode())
    signature = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(signature)}"


def read_session(token: str) -> dict | None:
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        data = json.loads(_unb64(payload))
        if int(data["exp"]) <= int(time.time()):
            return None
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
