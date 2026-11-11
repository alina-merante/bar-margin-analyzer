from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_session, require_session_csrf
from app.bar_context import get_user_bar_access
from app.database import get_db
from app.models import AuthSession, Bar, UserBarMembership

router = APIRouter(prefix="/auth", tags=["bar context"])


class ActiveBarRequest(BaseModel):
    bar_id: int


def _bar_response(bar: Bar, membership: UserBarMembership) -> dict:
    return {
        "id": bar.id,
        "name": bar.name,
        "role": membership.role.value,
    }


@router.get("/bars")
def list_accessible_bars(
    response: Response,
    auth_session: AuthSession = Depends(get_current_session),
    accesses=Depends(get_user_bar_access),
) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            **_bar_response(access.bar, access.membership),
            "selected": access.bar.id == auth_session.active_bar_id,
        }
        for access in accesses
    ]


@router.put("/active-bar")
def select_active_bar(
    payload: ActiveBarRequest,
    response: Response,
    auth_session: AuthSession = Depends(require_session_csrf),
    db: Session = Depends(get_db),
) -> dict:
    access = db.execute(
        select(Bar, UserBarMembership)
        .join(UserBarMembership, UserBarMembership.bar_id == Bar.id)
        .where(
            Bar.id == payload.bar_id,
            Bar.is_active.is_(True),
            UserBarMembership.user_id == auth_session.user_id,
        )
    ).first()
    if access is None:
        raise HTTPException(status_code=403, detail="bar access denied")

    bar, membership = access
    auth_session.active_bar_id = bar.id
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return _bar_response(bar, membership)


@router.get("/active-bar")
def read_active_bar(
    response: Response,
    auth_session: AuthSession = Depends(get_current_session),
    accesses=Depends(get_user_bar_access),
) -> dict | None:
    response.headers["Cache-Control"] = "no-store"
    if auth_session.active_bar_id is None:
        return None

    for access in accesses:
        if access.bar.id == auth_session.active_bar_id:
            return _bar_response(access.bar, access.membership)
    raise HTTPException(status_code=403, detail="active bar access denied")
