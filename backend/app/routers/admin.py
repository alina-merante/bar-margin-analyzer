import datetime as dt
import re
import secrets
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_session, require_global_admin, require_session_csrf
from app.database import get_db
from app.models import AdminAudit, AdminWriteLock, AuthSession, Bar, MembershipRole, User, UserBarMembership
from app.security import hash_password


class AdminRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(status_code=422, detail="invalid request") from exc

        return safe_handler


router = APIRouter(prefix="/admin", tags=["global administration"], route_class=AdminRoute)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BarCreate(StrictInput):
    name: str = Field(max_length=255)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class BarUpdate(StrictInput):
    name: str | None = Field(default=None, max_length=255)
    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("at least one non-null change is required")
        if self.name is not None:
            self.name = BarCreate.valid_name(self.name)
        return self


class UserCreate(StrictInput):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) > 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("valid email required")
        return normalized


class UserUpdate(StrictInput):
    email: str | None = Field(default=None, max_length=320)
    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("at least one non-null change is required")
        if self.email is not None:
            self.email = UserCreate.valid_email(self.email)
        return self


class AssignableRole(str, Enum):
    owner = "owner"
    staff = "staff"


class MembershipCreate(StrictInput):
    user_id: int = Field(gt=0, strict=True)
    role: AssignableRole


class MembershipUpdate(StrictInput):
    role: AssignableRole


def admin_read(
    response: Response,
    actor: User = Depends(require_global_admin),
) -> User:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers.add_vary_header("Cookie")
    return actor


def lock_admin_write(
    request: Request,
    actor: User,
    auth_session: AuthSession,
    db: Session,
    *,
    session_owner_id: int | None = None,
) -> User:
    result = db.execute(update(AdminWriteLock).where(AdminWriteLock.id == 1).values(id=1))
    if result.rowcount != 1:
        raise HTTPException(status_code=503, detail="administrative lock unavailable")
    db.execute(select(AuthSession.id).where(AuthSession.id == auth_session.id).with_for_update()).first()
    if session_owner_id is not None:
        # Tenant writes also lock sessions before their user.
        db.execute(
            select(AuthSession.id)
            .where(AuthSession.user_id == session_owner_id, AuthSession.revoked_at.is_(None))
            .order_by(AuthSession.id)
            .with_for_update()
        ).all()
    db.execute(select(User.id).where(User.id == actor.id).with_for_update()).first()
    db.expire_all()
    session = get_current_session(request, db)
    require_session_csrf(request, session)
    return require_global_admin(session.user)


def admin_write(
    request: Request,
    actor: User = Depends(admin_read),
    auth_session: AuthSession = Depends(require_session_csrf),
    db: Session = Depends(get_db),
) -> User:
    return lock_admin_write(request, actor, auth_session, db)


def admin_user_write(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(admin_read),
    auth_session: AuthSession = Depends(require_session_csrf),
    db: Session = Depends(get_db),
) -> User:
    return lock_admin_write(
        request, actor, auth_session, db,
        session_owner_id=user_id if payload.is_active is False else None,
    )


def bar_response(bar: Bar) -> dict:
    return {"id": bar.id, "name": bar.name, "is_active": bar.is_active}


def user_response(user: User) -> dict:
    return {
        "id": user.id, "email": user.email,
        "is_active": user.is_active, "is_global_admin": user.is_global_admin,
    }


def membership_response(membership: UserBarMembership) -> dict:
    return {
        "id": membership.id, "bar_id": membership.bar_id,
        "user_id": membership.user_id, "role": membership.role.value,
    }


def get_bar(db: Session, bar_id: int, *, lock: bool = False) -> Bar:
    query = select(Bar).where(Bar.id == bar_id)
    bar = db.scalar(query.with_for_update() if lock else query)
    if bar is None:
        raise HTTPException(status_code=404, detail="bar not found")
    return bar


def get_user(db: Session, user_id: int, *, lock: bool = False) -> User:
    query = select(User).where(User.id == user_id)
    user = db.scalar(query.with_for_update() if lock else query)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


def get_membership(db: Session, bar_id: int, user_id: int, *, lock: bool = False) -> UserBarMembership:
    query = select(UserBarMembership).where(
        UserBarMembership.bar_id == bar_id, UserBarMembership.user_id == user_id
    )
    membership = db.scalar(query.with_for_update() if lock else query)
    if membership is None:
        raise HTTPException(status_code=404, detail="membership not found")
    return membership


def audit(db: Session, actor: User, action: str, *, bar_id: int | None = None,
          user_id: int | None = None, changes: dict | None = None) -> None:
    db.add(AdminAudit(actor_id=actor.id, action=action, bar_id=bar_id,
                      user_id=user_id, changes=changes or {}))


def commit_unique(db: Session, *, constraint: str, sqlite_columns: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == constraint or sqlite_columns in str(exc.orig):
            raise HTTPException(status_code=409, detail="resource already exists") from exc
        raise


@router.get("/bars")
def list_bars(_actor: User = Depends(admin_read), db: Session = Depends(get_db)) -> list[dict]:
    return [bar_response(bar) for bar in db.scalars(select(Bar).order_by(Bar.id)).all()]


@router.post("/bars", status_code=201)
def create_bar(payload: BarCreate, actor: User = Depends(admin_write), db: Session = Depends(get_db)) -> dict:
    bar = Bar(name=payload.name)
    db.add(bar)
    db.flush()
    audit(db, actor, "bar.create", bar_id=bar.id, changes={"name": bar.name, "is_active": bar.is_active})
    db.commit()
    return bar_response(bar)


@router.get("/bars/{bar_id}")
def read_bar(bar_id: int, _actor: User = Depends(admin_read), db: Session = Depends(get_db)) -> dict:
    return bar_response(get_bar(db, bar_id))


@router.patch("/bars/{bar_id}")
def update_bar(bar_id: int, payload: BarUpdate, actor: User = Depends(admin_write),
               db: Session = Depends(get_db)) -> dict:
    bar = get_bar(db, bar_id, lock=True)
    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        old = getattr(bar, field)
        if old != value:
            changes[field] = {"from": old, "to": value}
            setattr(bar, field, value)
    if changes:
        audit(db, actor, "bar.update", bar_id=bar.id, changes=changes)
    db.commit()
    return bar_response(bar)


@router.get("/users")
def list_users(_actor: User = Depends(admin_read), db: Session = Depends(get_db)) -> list[dict]:
    return [user_response(user) for user in db.scalars(select(User).order_by(User.id)).all()]


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, actor: User = Depends(admin_write), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise HTTPException(status_code=409, detail="resource already exists")
    user = User(email=payload.email, password_hash=hash_password(secrets.token_urlsafe(48)))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == "uq_users_email" or "users.email" in str(exc.orig):
            raise HTTPException(status_code=409, detail="resource already exists") from exc
        raise
    audit(db, actor, "user.create", user_id=user.id, changes={"is_active": user.is_active})
    db.commit()
    return {**user_response(user), "password_setup_required": True}


@router.get("/users/{user_id}")
def read_user(user_id: int, _actor: User = Depends(admin_read), db: Session = Depends(get_db)) -> dict:
    return user_response(get_user(db, user_id))


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, actor: User = Depends(admin_user_write),
                db: Session = Depends(get_db)) -> dict:
    user = get_user(db, user_id, lock=True)
    values = payload.model_dump(exclude_unset=True)
    if values.get("is_active") is False and user.is_active and user.is_global_admin:
        count = db.scalar(select(func.count(User.id)).where(User.is_global_admin.is_(True), User.is_active.is_(True)))
        if count is None or count <= 1:
            raise HTTPException(status_code=409, detail="last active global administrator")
    if "email" in values and db.scalar(select(User.id).where(User.email == values["email"], User.id != user_id)):
        raise HTTPException(status_code=409, detail="resource already exists")
    changes = {}
    for field, value in values.items():
        old = getattr(user, field)
        if old != value:
            changes[field] = {"from": old, "to": value}
            setattr(user, field, value)
    if values.get("is_active") is False:
        result = db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=dt.datetime.now(dt.timezone.utc))
        )
        if result.rowcount:
            changes["sessions_revoked"] = result.rowcount
    if changes:
        audit(db, actor, "user.update", user_id=user.id, changes=changes)
    commit_unique(db, constraint="uq_users_email", sqlite_columns="users.email")
    return user_response(user)


@router.get("/bars/{bar_id}/memberships")
def list_memberships(bar_id: int, _actor: User = Depends(admin_read), db: Session = Depends(get_db)) -> list[dict]:
    get_bar(db, bar_id)
    rows = db.execute(
        select(UserBarMembership, User)
        .join(User, User.id == UserBarMembership.user_id)
        .where(UserBarMembership.bar_id == bar_id)
        .order_by(UserBarMembership.id)
    ).all()
    return [{**membership_response(membership), "user": user_response(user)} for membership, user in rows]


@router.post("/bars/{bar_id}/memberships", status_code=201)
def create_membership(bar_id: int, payload: MembershipCreate, actor: User = Depends(admin_write),
                      db: Session = Depends(get_db)) -> dict:
    get_user(db, payload.user_id, lock=True)
    get_bar(db, bar_id, lock=True)
    if db.scalar(select(UserBarMembership.id).where(
        UserBarMembership.user_id == payload.user_id, UserBarMembership.bar_id == bar_id
    )):
        raise HTTPException(status_code=409, detail="resource already exists")
    membership = UserBarMembership(user_id=payload.user_id, bar_id=bar_id, role=MembershipRole(payload.role.value))
    db.add(membership)
    audit(db, actor, "membership.create", bar_id=bar_id, user_id=payload.user_id,
          changes={"role": payload.role.value})
    commit_unique(db, constraint="uq_user_bar_memberships_user_bar",
                  sqlite_columns="user_bar_memberships.user_id, user_bar_memberships.bar_id")
    return membership_response(membership)


@router.patch("/bars/{bar_id}/memberships/{user_id}")
def update_membership(bar_id: int, user_id: int, payload: MembershipUpdate,
                      actor: User = Depends(admin_write), db: Session = Depends(get_db)) -> dict:
    get_user(db, user_id, lock=True)
    get_bar(db, bar_id, lock=True)
    membership = get_membership(db, bar_id, user_id, lock=True)
    old_role = membership.role.value
    if old_role != payload.role.value:
        membership.role = MembershipRole(payload.role.value)
        membership.permissions.clear()
        audit(db, actor, "membership.role", bar_id=bar_id, user_id=user_id,
              changes={"role": {"from": old_role, "to": payload.role.value}})
    db.commit()
    return membership_response(membership)


@router.delete("/bars/{bar_id}/memberships/{user_id}")
def delete_membership(bar_id: int, user_id: int, actor: User = Depends(admin_write),
                      db: Session = Depends(get_db)) -> dict:
    get_user(db, user_id, lock=True)
    get_bar(db, bar_id, lock=True)
    membership = get_membership(db, bar_id, user_id, lock=True)
    audit(db, actor, "membership.delete", bar_id=bar_id, user_id=user_id,
          changes={"role": membership.role.value})
    db.delete(membership)
    db.commit()
    return {"revoked": True}
