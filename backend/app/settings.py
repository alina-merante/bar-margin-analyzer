import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _origins_from_environment(environment: str) -> tuple[str, ...]:
    configured = os.getenv("AUTH_ALLOWED_ORIGINS")
    if configured is None:
        if environment == "production":
            raise RuntimeError(
                "AUTH_ALLOWED_ORIGINS must be configured in production."
            )
        return (
            "https://verbose-waddle-97gxgpv5qqgx3x7r7-5173.app.github.dev",
            "http://localhost:5173",
        )
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    )
    if not origins or "*" in origins:
        raise RuntimeError("AUTH_ALLOWED_ORIGINS must be a non-empty explicit list.")
    return origins


@dataclass(frozen=True)
class AuthSettings:
    environment: str
    secret_key: bytes
    cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int
    pre_auth_csrf_ttl_seconds: int
    login_attempt_limit: int
    login_source_attempt_limit: int
    login_attempt_window_seconds: int
    allowed_origins: tuple[str, ...]


def _load_settings() -> AuthSettings:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    secret_value = os.getenv("AUTH_SECRET_KEY")
    if environment == "production":
        if not secret_value or len(secret_value.encode("utf-8")) < 32:
            raise RuntimeError(
                "AUTH_SECRET_KEY must contain at least 32 bytes in production."
            )
        if os.getenv("AUTH_COOKIE_SECURE", "true").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise RuntimeError("AUTH_COOKIE_SECURE cannot be disabled in production.")
        secret_key = secret_value.encode("utf-8")
        cookie_secure = True
    else:
        secret_key = (
            secret_value.encode("utf-8")
            if secret_value
            else secrets.token_bytes(32)
        )
        cookie_secure = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    session_ttl_seconds = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "43200"))
    pre_auth_csrf_ttl_seconds = int(os.getenv("AUTH_CSRF_TTL_SECONDS", "600"))
    login_attempt_limit = int(os.getenv("AUTH_LOGIN_ATTEMPT_LIMIT", "5"))
    login_source_attempt_limit = int(
        os.getenv("AUTH_LOGIN_SOURCE_ATTEMPT_LIMIT", "50")
    )
    login_attempt_window_seconds = int(
        os.getenv("AUTH_LOGIN_ATTEMPT_WINDOW_SECONDS", "900")
    )
    if min(
        session_ttl_seconds,
        pre_auth_csrf_ttl_seconds,
        login_attempt_limit,
        login_source_attempt_limit,
        login_attempt_window_seconds,
    ) < 1:
        raise RuntimeError("Authentication timeouts and limits must be positive.")

    return AuthSettings(
        environment=environment,
        secret_key=secret_key,
        cookie_name=os.getenv("AUTH_COOKIE_NAME", "barmanager_session"),
        cookie_secure=cookie_secure,
        session_ttl_seconds=session_ttl_seconds,
        pre_auth_csrf_ttl_seconds=pre_auth_csrf_ttl_seconds,
        login_attempt_limit=login_attempt_limit,
        login_source_attempt_limit=login_source_attempt_limit,
        login_attempt_window_seconds=login_attempt_window_seconds,
        allowed_origins=_origins_from_environment(environment),
    )


settings = _load_settings()
