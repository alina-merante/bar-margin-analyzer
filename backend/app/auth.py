import datetime as dt
import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, User
from app.security import token_hash
from app.settings import settings


def require_allowed_origin(request: Request) -> None:
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or origin not in settings.allowed_origins:
        raise HTTPException(status_code=403, detail="untrusted request origin")


def find_session(request: Request, db: Session) -> AuthSession | None:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None
    return db.scalar(
        select(AuthSession)
        .where(
            AuthSession.token_hash == token_hash(token),
            AuthSession.revoked_at.is_(None),
        )
    )


def session_is_active(auth_session: AuthSession, now: dt.datetime | None = None) -> bool:
    current_time = now or dt.datetime.now(dt.timezone.utc)
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    return auth_session.revoked_at is None and expires_at > current_time


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthSession:
    auth_session = find_session(request, db)
    if auth_session is None or not session_is_active(auth_session):
        raise HTTPException(status_code=401, detail="authentication required")
    if not auth_session.user.is_active:
        raise HTTPException(status_code=401, detail="authentication required")
    return auth_session


def get_current_user(
    auth_session: AuthSession = Depends(get_current_session),
) -> User:
    return auth_session.user


def require_global_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_active or not user.is_global_admin:
        raise HTTPException(status_code=403, detail="global administrator required")
    return user


def require_session_csrf(
    request: Request,
    auth_session: AuthSession = Depends(get_current_session),
) -> AuthSession:
    csrf_cookie = request.cookies.get("barmanager_csrf", "")
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
    require_allowed_origin(request)
    return auth_session
