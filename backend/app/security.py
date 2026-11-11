import datetime as dt
import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.settings import settings

PASSWORD_HASHER = PasswordHasher(type=Type.ID)
_DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 1024:
        raise ValueError("Password must contain at most 1024 characters.")
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def dummy_password_hash() -> str:
    return _DUMMY_PASSWORD_HASH


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def keyed_hash(value: str) -> str:
    return hmac.new(
        settings.secret_key,
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_pre_auth_csrf_token(now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    nonce = secrets.token_urlsafe(32)
    payload = f"preauth:{issued_at}:{nonce}"
    signature = hmac.new(
        settings.secret_key,
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{issued_at}.{nonce}.{signature}"


def verify_pre_auth_csrf_token(token: str, now: int | None = None) -> bool:
    try:
        issued_at_text, nonce, signature = token.split(".", 2)
        issued_at = int(issued_at_text)
    except (AttributeError, ValueError):
        return False
    current_time = int(time.time()) if now is None else now
    age = current_time - issued_at
    if age < 0 or age > settings.pre_auth_csrf_ttl_seconds or not nonce:
        return False
    payload = f"preauth:{issued_at}:{nonce}"
    expected_signature = hmac.new(
        settings.secret_key,
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def new_session_values() -> tuple[str, str, dt.datetime, dt.datetime]:
    now = dt.datetime.now(dt.timezone.utc)
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = now + dt.timedelta(seconds=settings.session_ttl_seconds)
    return token, csrf_token, now, expires_at
