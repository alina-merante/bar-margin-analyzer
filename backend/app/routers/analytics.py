import datetime as dt
from decimal import Decimal

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


def parse_year(year: str) -> tuple[dt.date, dt.date]:
    try:
        start = dt.datetime.strptime(year, "%Y").date().replace(month=1, day=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="year must be in YYYY format") from exc
    return start, start.replace(year=start.year + 1)


def previous_month(month_start: dt.date) -> tuple[dt.date, dt.date]:
    prev_end = month_start
    if month_start.month == 1:
        prev_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_start = month_start.replace(month=month_start.month - 1)
    return prev_start, prev_end


def sum_revenue(db: Session, start: dt.date, end: dt.date) -> Decimal:
    revenue = db.execute(select(func.coalesce(func.sum(SaleLine.total), 0)).where(SaleLine.date >= start, SaleLine.date < end))
    return Decimal(revenue.scalar_one())


def sum_expenses(db: Session, start: dt.date, end: dt.date) -> Decimal:
    expenses = db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.amount < 0,
        )
    )
    return Decimal(expenses.scalar_one())


def monthly_pnl(db: Session, start: dt.date, end: dt.date) -> dict[str, Decimal]:
    revenue = sum_revenue(db, start, end)
    expenses = sum_expenses(db, start, end)
    return {
        "revenue": revenue,
        "expenses": expenses,
        "profit": revenue - expenses,
    }


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


@router.get("/pnl")
def pnl(month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)) -> dict:
    start, end = parse_month(month)
    current = monthly_pnl(db, start, end)

    prev_start, prev_end = previous_month(start)
    previous = monthly_pnl(db, prev_start, prev_end)

    return {
        "month": month,
        "revenue": float(current["revenue"]),
        "expenses": float(current["expenses"]),
        "profit": float(current["profit"]),
        "previous_month_revenue": float(previous["revenue"]),
        "previous_month_expenses": float(previous["expenses"]),
        "previous_month_profit": float(previous["profit"]),
        "revenue_delta": float(current["revenue"] - previous["revenue"]),
        "expenses_delta": float(current["expenses"] - previous["expenses"]),
        "profit_delta": float(current["profit"] - previous["profit"]),
    }


@router.get("/pnl/ytd")
def pnl_ytd(year: str = Query(..., description="Year in YYYY format"), db: Session = Depends(get_db)) -> dict:
    start, end = parse_year(year)
    ytd = monthly_pnl(db, start, end)

    monthly_breakdown: list[dict[str, float | str]] = []
    current_month = start
    while current_month < end:
        if current_month.month == 12:
            next_month = current_month.replace(year=current_month.year + 1, month=1)
        else:
            next_month = current_month.replace(month=current_month.month + 1)
        month_values = monthly_pnl(db, current_month, next_month)
        monthly_breakdown.append(
            {
                "month": current_month.strftime("%Y-%m"),
                "revenue": float(month_values["revenue"]),
                "expenses": float(month_values["expenses"]),
                "profit": float(month_values["profit"]),
            }
        )
        current_month = next_month

    return {
        "year": year,
        "revenue_ytd": float(ytd["revenue"]),
        "expenses_ytd": float(ytd["expenses"]),
        "profit_ytd": float(ytd["profit"]),
        "monthly_breakdown": monthly_breakdown,
    }


@router.get("/overview")
def overview(
    month: str | None = Query(default=None, description="Optional month in YYYY-MM format"),
    db: Session = Depends(get_db),
) -> dict:
    selected_month = month or dt.date.today().strftime("%Y-%m")
    start, end = parse_month(selected_month)
    pnl_summary = monthly_pnl(db, start, end)

    top_products_by_quantity = db.execute(
        select(
            Product.name.label("product"),
            func.sum(SaleLine.qty).label("quantity"),
            func.sum(SaleLine.total).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .where(SaleLine.date >= start, SaleLine.date < end)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(SaleLine.qty).desc())
        .limit(10)
    ).all()

    top_products_by_revenue = db.execute(
        select(
            Product.name.label("product"),
            func.sum(SaleLine.qty).label("quantity"),
            func.sum(SaleLine.total).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .where(SaleLine.date >= start, SaleLine.date < end)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(SaleLine.total).desc())
        .limit(10)
    ).all()

    top_expense_categories = db.execute(
        select(
            ExpenseCategory.name.label("category"),
            func.sum(func.abs(Transaction.amount)).label("expenses"),
        )
        .outerjoin(ExpenseCategory, Transaction.category_id == ExpenseCategory.id)
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(ExpenseCategory.name)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    ).all()

    top_suppliers = db.execute(
        select(
            Transaction.counterparty.label("supplier"),
            func.sum(func.abs(Transaction.amount)).label("expenses"),
        )
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(Transaction.counterparty)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    ).all()

    return {
        "top_products_by_quantity": [
            {"product": row.product, "quantity": float(row.quantity), "revenue": float(row.revenue)}
            for row in top_products_by_quantity
        ],
        "top_products_by_revenue": [
            {"product": row.product, "quantity": float(row.quantity), "revenue": float(row.revenue)}
            for row in top_products_by_revenue
        ],
        "top_expense_categories": [
            {"category": row.category or "Uncategorized", "expenses": float(row.expenses)} for row in top_expense_categories
        ],
        "top_suppliers": [{"supplier": row.supplier, "expenses": float(row.expenses)} for row in top_suppliers],
        "pnl_summary": {
            "month": selected_month,
            "revenue": float(pnl_summary["revenue"]),
            "expenses": float(pnl_summary["expenses"]),
            "profit": float(pnl_summary["profit"]),
        },
    }


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
