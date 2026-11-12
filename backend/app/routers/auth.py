import datetime as dt
import hmac
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import (
    find_session,
    get_current_session,
    require_allowed_origin,
    session_is_active,
)
from app.database import get_db
from app.models import AuthLoginAttempt, AuthSession, User
from app.security import (
    create_pre_auth_csrf_token,
    dummy_password_hash,
    hash_password,
    keyed_hash,
    new_session_values,
    token_hash,
    verify_password,
    verify_pre_auth_csrf_token,
)
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("A valid email address is required.")
        return normalized

    @field_validator("password")
    @classmethod
    def limit_password_size(cls, value: str) -> str:
        if len(value) > 1024:
            raise ValueError("Password must contain at most 1024 characters.")
        return value


def _csrf_cookie_name() -> str:
    return "barmanager_csrf"


def _set_csrf_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        _csrf_cookie_name(),
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        settings.cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        _csrf_cookie_name(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _validate_pre_auth_csrf(request: Request) -> str:
    cookie_token = request.cookies.get(_csrf_cookie_name(), "")
    header_token = request.headers.get("x-csrf-token", "")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not verify_pre_auth_csrf_token(header_token)
    ):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    return header_token


def _login_keys(email: str, request: Request) -> tuple[str, str]:
    source = request.client.host if request.client is not None else "unknown"
    return keyed_hash(f"email:{email}"), keyed_hash(f"source:{source}")


def _check_login_rate_limit(
    db: Session,
    email_key: str,
    source_key: str,
    now: dt.datetime,
) -> None:
    cutoff = now - dt.timedelta(seconds=settings.login_attempt_window_seconds)
    db.execute(
        delete(AuthLoginAttempt).where(AuthLoginAttempt.attempted_at < cutoff)
    )
    email_source_count = db.scalar(
        select(func.count(AuthLoginAttempt.id)).where(
            AuthLoginAttempt.attempted_at >= cutoff,
            AuthLoginAttempt.email_key == email_key,
            AuthLoginAttempt.source_key == source_key,
        )
    ) or 0
    source_count = db.scalar(
        select(func.count(AuthLoginAttempt.id)).where(
            AuthLoginAttempt.attempted_at >= cutoff,
            AuthLoginAttempt.source_key == source_key,
        )
    ) or 0
    if (
        email_source_count >= settings.login_attempt_limit
        or source_count >= settings.login_source_attempt_limit
    ):
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail="too many login attempts; try again later",
            headers={"Retry-After": str(settings.login_attempt_window_seconds)},
        )


@router.get("/csrf")
def issue_csrf_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    auth_session = find_session(request, db)
    if auth_session is not None and session_is_active(auth_session):
        csrf_token = secrets.token_urlsafe(32)
        auth_session.csrf_token_hash = token_hash(csrf_token)
        db.commit()
        _set_csrf_cookie(response, csrf_token, settings.session_ttl_seconds)
    else:
        csrf_token = create_pre_auth_csrf_token()
        _set_csrf_cookie(response, csrf_token, settings.pre_auth_csrf_ttl_seconds)
    return {"csrf_token": csrf_token}


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    require_allowed_origin(request)
    _validate_pre_auth_csrf(request)

    email = payload.email
    email_key, source_key = _login_keys(email, request)
    now = dt.datetime.now(dt.timezone.utc)
    _check_login_rate_limit(db, email_key, source_key, now)

    # Serialize session issuance with account deactivation.
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    valid_password = verify_password(payload.password, password_hash)
    if user is None or not valid_password or not user.is_active:
        db.add(
            AuthLoginAttempt(
                email_key=email_key,
                source_key=source_key,
                attempted_at=now,
            )
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid email or password")

    token, csrf_token, created_at, expires_at = new_session_values()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_token_hash=token_hash(csrf_token),
        created_at=created_at,
        expires_at=expires_at,
    )
    db.add(auth_session)
    db.execute(
        delete(AuthLoginAttempt).where(AuthLoginAttempt.email_key == email_key)
    )
    db.commit()

    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    _set_csrf_cookie(response, csrf_token, settings.session_ttl_seconds)
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": {"id": user.id, "email": user.email},
        "expires_at": expires_at.isoformat(),
        "csrf_token": csrf_token,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    require_allowed_origin(request)
    auth_session = find_session(request, db)
    if auth_session is not None and session_is_active(auth_session):
        csrf_cookie = request.cookies.get(_csrf_cookie_name(), "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
            or not hmac.compare_digest(
                token_hash(csrf_header),
                auth_session.csrf_token_hash,
            )
        ):
            raise HTTPException(status_code=403, detail="invalid CSRF token")
        auth_session.revoked_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    else:
        csrf_cookie = request.cookies.get(_csrf_cookie_name(), "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
        ):
            raise HTTPException(status_code=403, detail="invalid CSRF token")
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = dt.datetime.now(dt.timezone.utc)
            db.commit()

    _clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return {"logged_out": True}


@router.get("/session")
def current_session(
    response: Response,
    auth_session: AuthSession = Depends(get_current_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": {
            "id": auth_session.user.id,
            "email": auth_session.user.email,
        },
        "expires_at": auth_session.expires_at.isoformat(),
    }
