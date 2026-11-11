from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_session_csrf
from app.bar_context import BarContext, BarPermission, require_bar_permission
from app.database import get_db
from app.models import AuthSession, CategoryRule, ExpenseCategory

router = APIRouter(tags=["categories", "rules"])
operational_context = require_bar_permission(BarPermission.OPERATE)


class CategoryCreate(BaseModel):
    name: str


class RuleCreate(BaseModel):
    keyword: str
    category_id: int


@router.post("/categories")
def create_category(
    payload: CategoryCreate,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(operational_context),
    db: Session = Depends(get_db),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    existing = db.scalar(
        select(ExpenseCategory).where(
            ExpenseCategory.bar_id == context.bar.id,
            ExpenseCategory.name == name,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="category already exists")

    category = ExpenseCategory(name=name, bar_id=context.bar.id)
    db.add(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="category already exists") from exc
    db.refresh(category)
    return {"id": category.id, "name": category.name}


@router.get("/categories")
def list_categories(
    context: BarContext = Depends(operational_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(ExpenseCategory)
        .where(ExpenseCategory.bar_id == context.bar.id)
        .order_by(ExpenseCategory.name.asc())
    ).all()
    return [{"id": row.id, "name": row.name} for row in rows]


@router.post("/rules")
def create_rule(
    payload: RuleCreate,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(operational_context),
    db: Session = Depends(get_db),
) -> dict:
    keyword = payload.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")

    category = db.scalar(
        select(ExpenseCategory).where(
            ExpenseCategory.id == payload.category_id,
            ExpenseCategory.bar_id == context.bar.id,
        )
    )
    if not category:
        raise HTTPException(status_code=404, detail="category not found")

    rule = CategoryRule(
        bar_id=context.bar.id,
        keyword=keyword,
        category_id=category.id,
    )
    db.add(rule)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="category rule conflicts with existing data",
        ) from exc
    db.refresh(rule)
    return {"id": rule.id, "keyword": rule.keyword, "category_id": rule.category_id}


@router.get("/rules")
def list_rules(
    context: BarContext = Depends(operational_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(CategoryRule)
        .where(CategoryRule.bar_id == context.bar.id)
        .order_by(CategoryRule.id.asc())
    ).all()
    return [{"id": row.id, "keyword": row.keyword, "category_id": row.category_id} for row in rows]
