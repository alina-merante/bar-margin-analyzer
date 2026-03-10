from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategoryRule, ExpenseCategory

router = APIRouter(tags=["categories", "rules"])


class CategoryCreate(BaseModel):
    name: str


class RuleCreate(BaseModel):
    keyword: str
    category_id: int


@router.post("/categories")
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    existing = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name))
    if existing:
        raise HTTPException(status_code=400, detail="category already exists")

    category = ExpenseCategory(name=name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return {"id": category.id, "name": category.name}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name.asc())).all()
    return [{"id": row.id, "name": row.name} for row in rows]


@router.post("/rules")
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)) -> dict:
    keyword = payload.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")

    category = db.get(ExpenseCategory, payload.category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category not found")

    rule = CategoryRule(keyword=keyword, category_id=payload.category_id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "keyword": rule.keyword, "category_id": rule.category_id}


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(CategoryRule).order_by(CategoryRule.id.asc())).all()
    return [{"id": row.id, "keyword": row.keyword, "category_id": row.category_id} for row in rows]
