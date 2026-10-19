import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt

from .config import settings
from .models import utcnow


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hmac_hex(message: str | bytes, key: str | None = None) -> str:
    if isinstance(message, str):
        message = message.encode()
    return hmac.new((key or settings.jwt_secret).encode(), message, hashlib.sha256).hexdigest()


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def create_access_token(user_id: int, session_id: int) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == "access" else None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)
