import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ExpenseCategory, Product, SaleLine, Transaction

router = APIRouter(prefix="/analytics", tags=["analytics"])


def parse_month(month: str) -> tuple[dt.date, dt.date]:
    try:
        start = dt.datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format") from exc

    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def fetch_ranked_products(db: Session, month: str, order: str) -> dict:
    start, end = parse_month(month)

    quantity_order = func.sum(SaleLine.qty).desc() if order == "desc" else func.sum(SaleLine.qty).asc()
    revenue_order = func.sum(SaleLine.total).desc() if order == "desc" else func.sum(SaleLine.total).asc()

    qty_rows = db.execute(
        select(
            Product.name.label("product"),
            func.sum(SaleLine.qty).label("quantity"),
            func.sum(SaleLine.total).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .where(SaleLine.date >= start, SaleLine.date < end)
        .group_by(Product.id, Product.name)
        .order_by(quantity_order)
        .limit(10)
    ).all()

    revenue_rows = db.execute(
        select(
            Product.name.label("product"),
            func.sum(SaleLine.qty).label("quantity"),
            func.sum(SaleLine.total).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .where(SaleLine.date >= start, SaleLine.date < end)
        .group_by(Product.id, Product.name)
        .order_by(revenue_order)
        .limit(10)
    ).all()

    return {
        "month": month,
        "by_quantity": [
            {
                "rank": idx,
                "product": row.product,
                "quantity": float(row.quantity),
                "revenue": float(row.revenue),
            }
            for idx, row in enumerate(qty_rows, start=1)
        ],
        "by_revenue": [
            {
                "rank": idx,
                "product": row.product,
                "quantity": float(row.quantity),
                "revenue": float(row.revenue),
            }
            for idx, row in enumerate(revenue_rows, start=1)
        ],
    }


@router.get("/top-products")
def top_products(month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)):
    return fetch_ranked_products(db, month, order="desc")


@router.get("/bottom-products")
def bottom_products(month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)):
    return fetch_ranked_products(db, month, order="asc")


@router.get("/expenses-by-category")
def expenses_by_category(
    month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)
) -> dict:
    start, end = parse_month(month)

    rows = db.execute(
        select(
            ExpenseCategory.name.label("category"),
            func.sum(Transaction.amount).label("total_amount"),
        )
        .outerjoin(ExpenseCategory, Transaction.category_id == ExpenseCategory.id)
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(ExpenseCategory.name)
        .order_by(func.abs(func.sum(Transaction.amount)).desc())
    ).all()

    return {
        "month": month,
        "items": [
            {
                "category": row.category or "Uncategorized",
                "total_amount": float(row.total_amount),
            }
            for row in rows
        ],
    }


@router.get("/expenses-by-supplier")
def expenses_by_supplier(
    month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)
) -> dict:
    start, end = parse_month(month)

    rows = db.execute(
        select(
            Transaction.counterparty.label("counterparty"),
            func.sum(Transaction.amount).label("total_amount"),
        )
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(Transaction.counterparty)
        .order_by(func.abs(func.sum(Transaction.amount)).desc())
    ).all()

    return {
        "month": month,
        "items": [
            {
                "counterparty": row.counterparty,
                "total_amount": float(row.total_amount),
            }
            for row in rows
        ],
    }
