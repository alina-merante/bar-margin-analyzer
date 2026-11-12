from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_session
from app.database import get_db
from app.models import (
    AuthSession,
    Bar,
    MembershipRole,
    User,
    UserBarMembership,
)

EXPECTED_BAR_HEADER = "X-Expected-Bar-ID"


@dataclass(frozen=True)
class BarAccess:
    bar: Bar
    membership: UserBarMembership


@dataclass(frozen=True)
class BarContext:
    auth_session: AuthSession
    user: User
    bar: Bar
    membership: UserBarMembership

    @property
    def role(self) -> MembershipRole:
        return self.membership.role


class BarPermission(str, Enum):
    MANAGE_BAR = "manage_bar"
    MANAGE_USERS = "manage_users"
    OPERATE = "operate"
    READ_DOCUMENTS = "read_documents"
    UPLOAD_DOCUMENTS = "upload_documents"
    REVIEW_OCR = "review_ocr"
    DELETE_RECORDS = "delete_records"
    MANAGE_PAYMENTS = "manage_payments"


_ROLE_PERMISSIONS: dict[MembershipRole, frozenset[BarPermission]] = {
    MembershipRole.owner: frozenset(BarPermission),
    MembershipRole.manager: frozenset(
        {
            BarPermission.OPERATE,
            BarPermission.READ_DOCUMENTS,
            BarPermission.UPLOAD_DOCUMENTS,
            BarPermission.REVIEW_OCR,
            BarPermission.DELETE_RECORDS,
            BarPermission.MANAGE_PAYMENTS,
        }
    ),
    MembershipRole.staff: frozenset(
        {
            BarPermission.READ_DOCUMENTS,
            BarPermission.UPLOAD_DOCUMENTS,
            BarPermission.REVIEW_OCR,
        }
    ),
}


def get_user_bar_access(
    auth_session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> list[BarAccess]:
    rows = db.execute(
        select(Bar, UserBarMembership)
        .join(UserBarMembership, UserBarMembership.bar_id == Bar.id)
        .where(
            UserBarMembership.user_id == auth_session.user_id,
            Bar.is_active.is_(True),
        )
        .order_by(Bar.name.asc(), Bar.id.asc())
    ).all()
    return [BarAccess(bar=bar, membership=membership) for bar, membership in rows]


def get_expected_bar_id(
    value: str | None = Header(default=None, alias=EXPECTED_BAR_HEADER),
) -> int | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise HTTPException(status_code=400, detail="invalid expected bar id")
    return int(value)


def get_active_bar_context(
    request: Request,
    auth_session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
    expected_bar_id: int | None = Depends(get_expected_bar_id),
) -> BarContext:
    if auth_session.active_bar_id is None:
        raise HTTPException(status_code=409, detail="no active bar selected")
    if expected_bar_id is None:
        raise HTTPException(
            status_code=428,
            detail=f"{EXPECTED_BAR_HEADER} header is required",
        )

    if expected_bar_id != auth_session.active_bar_id:
        raise HTTPException(status_code=409, detail="active bar does not match request")

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        auth_session = lock_active_bar_context(
            request, auth_session, db, expected_bar_id
        )
        if auth_session.active_bar_id != expected_bar_id:
            raise HTTPException(status_code=409, detail="active bar does not match request")

    return resolve_active_bar_context(auth_session, db, expected_bar_id)


def parse_expected_bar_id(request: Request) -> int:
    expected_bar_id = get_expected_bar_id(
        request.headers.get(EXPECTED_BAR_HEADER)
    )
    if expected_bar_id is None:
        raise HTTPException(
            status_code=428,
            detail=f"{EXPECTED_BAR_HEADER} header is required",
        )
    return expected_bar_id


def resolve_active_bar_context(
    auth_session: AuthSession,
    db: Session,
    expected_bar_id: int,
) -> BarContext:
    if auth_session.active_bar_id is None:
        raise HTTPException(status_code=409, detail="no active bar selected")
    if expected_bar_id != auth_session.active_bar_id:
        raise HTTPException(status_code=409, detail="active bar does not match request")

    access = db.execute(
        select(Bar, UserBarMembership)
        .join(UserBarMembership, UserBarMembership.bar_id == Bar.id)
        .where(
            Bar.id == expected_bar_id,
            Bar.is_active.is_(True),
            UserBarMembership.user_id == auth_session.user_id,
        )
    ).first()
    if access is None:
        raise HTTPException(status_code=403, detail="active bar access denied")

    bar, membership = access
    return BarContext(
        auth_session=auth_session,
        user=auth_session.user,
        bar=bar,
        membership=membership,
    )


def lock_active_bar_context(
    request: Request,
    auth_session: AuthSession,
    db: Session,
    bar_id: int,
) -> AuthSession:
    db.execute(
        select(AuthSession.id)
        .where(AuthSession.id == auth_session.id)
        .with_for_update()
    ).first()
    db.execute(
        select(User.id).where(User.id == auth_session.user_id).with_for_update()
    ).first()
    db.execute(select(Bar.id).where(Bar.id == bar_id).with_for_update()).first()
    db.execute(
        select(UserBarMembership.id)
        .where(
            UserBarMembership.user_id == auth_session.user_id,
            UserBarMembership.bar_id == bar_id,
        )
        .with_for_update()
    ).first()
    db.expire_all()
    return get_current_session(request, db)


def revalidate_active_bar_context(
    request: Request,
    db: Session,
    bar_id: int,
    *,
    lock: bool = False,
) -> BarContext:
    expected_bar_id = parse_expected_bar_id(request)
    db.flush()
    db.expire_all()
    auth_session = get_current_session(request, db)
    if lock:
        auth_session = lock_active_bar_context(request, auth_session, db, bar_id)

    context = resolve_active_bar_context(auth_session, db, expected_bar_id)
    if context.bar.id != bar_id:
        raise HTTPException(status_code=409, detail="active bar changed during operation")
    return context


def require_bar_permission(permission: BarPermission):
    def dependency(
        context: BarContext = Depends(get_active_bar_context),
    ) -> BarContext:
        if permission not in _ROLE_PERMISSIONS[context.role]:
            raise HTTPException(status_code=403, detail="bar permission denied")
        return context

    return dependency


def require_owner(
    context: BarContext = Depends(get_active_bar_context),
) -> BarContext:
    if context.role != MembershipRole.owner:
        raise HTTPException(status_code=403, detail="owner role required")
    return context


def require_manager_or_owner(
    context: BarContext = Depends(get_active_bar_context),
) -> BarContext:
    if context.role not in {MembershipRole.owner, MembershipRole.manager}:
        raise HTTPException(status_code=403, detail="manager role required")
    return context
