import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ExpenseCategory, Invoice, InvoiceStatus, Payment, Product, SaleLine, Transaction

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


def round_money(value: Decimal) -> float:
    return round(float(value), 2)


def round_pct(value: Decimal) -> float:
    return round(float(value), 2)


def calculate_change_pct(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        if current == 0:
            return Decimal("0")
        return Decimal("100") if current > 0 else Decimal("-100")
    return ((current - previous) / abs(previous)) * Decimal("100")


def ratio_pct(part: Decimal, whole: Decimal) -> Decimal:
    if whole == 0:
        return Decimal("0")
    return (part / whole) * Decimal("100")


def top_expense_category(db: Session, start: dt.date, end: dt.date):
    return db.execute(
        select(
            ExpenseCategory.name.label("category"),
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("expenses"),
        )
        .outerjoin(ExpenseCategory, Transaction.category_id == ExpenseCategory.id)
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(ExpenseCategory.name)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(1)
    ).first()


def category_expense_sum(db: Session, start: dt.date, end: dt.date, category_name: str | None) -> Decimal:
    filters = [Transaction.date >= start, Transaction.date < end, Transaction.amount < 0]
    if category_name is None:
        filters.append(ExpenseCategory.name.is_(None))
    else:
        filters.append(ExpenseCategory.name == category_name)

    value = db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .select_from(Transaction)
        .outerjoin(ExpenseCategory, Transaction.category_id == ExpenseCategory.id)
        .where(*filters)
    )
    return Decimal(value.scalar_one())


def top_supplier(db: Session, start: dt.date, end: dt.date):
    return db.execute(
        select(
            Transaction.counterparty.label("supplier"),
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("expenses"),
        )
        .where(Transaction.date >= start, Transaction.date < end, Transaction.amount < 0)
        .group_by(Transaction.counterparty)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(1)
    ).first()


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


@router.get("/insights")
def insights(month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)) -> dict:
    start, end = parse_month(month)
    prev_start, prev_end = previous_month(start)

    current = monthly_pnl(db, start, end)
    previous = monthly_pnl(db, prev_start, prev_end)

    revenue_change = calculate_change_pct(current["revenue"], previous["revenue"])
    expenses_change = calculate_change_pct(current["expenses"], previous["expenses"])
    profit_change = calculate_change_pct(current["profit"], previous["profit"])

    generated_insights: list[str] = []
    metric_insights = [
        ("Revenue", revenue_change),
        ("Expenses", expenses_change),
        ("Profit", profit_change),
    ]
    for label, change in metric_insights:
        if abs(change) > Decimal("5"):
            direction = "increased" if change > 0 else "decreased"
            generated_insights.append(f"{label} {direction} by {round_pct(change)}% vs previous month.")

    top_category = top_expense_category(db, start, end)
    if top_category and top_category.expenses and Decimal(top_category.expenses) > 0:
        current_category_expenses = Decimal(top_category.expenses)
        previous_category_expenses = category_expense_sum(db, prev_start, prev_end, top_category.category)
        category_change = calculate_change_pct(current_category_expenses, previous_category_expenses)
        if abs(category_change) > Decimal("10"):
            category_name = top_category.category or "Uncategorized"
            direction = "increased" if category_change > 0 else "decreased"
            generated_insights.append(
                f"Top expense category '{category_name}' {direction} by {round_pct(category_change)}% vs previous month."
            )

    top_supplier_row = top_supplier(db, start, end)
    if top_supplier_row and top_supplier_row.expenses and current["expenses"] > 0:
        supplier_expense = Decimal(top_supplier_row.expenses)
        supplier_share = ratio_pct(supplier_expense, current["expenses"])
        generated_insights.append(
            f"Top supplier '{top_supplier_row.supplier}' represents {round_pct(supplier_share)}% of total expenses."
        )

    return {
        "month": month,
        "insights": generated_insights,
        "metrics": {
            "revenue": round_money(current["revenue"]),
            "expenses": round_money(current["expenses"]),
            "profit": round_money(current["profit"]),
            "revenue_change_pct": round_pct(revenue_change),
            "expenses_change_pct": round_pct(expenses_change),
            "profit_change_pct": round_pct(profit_change),
        },
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

@router.get("/invoices-summary")
def invoices_summary(db: Session = Depends(get_db)) -> dict:
    total_invoices = db.scalar(select(func.count(Invoice.id))) or 0
    pending_invoices = db.scalar(select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.pending)) or 0
    paid_invoices = db.scalar(select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.paid)) or 0

    pending_amount = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(Invoice.status == InvoiceStatus.pending)
    ) or 0
    paid_amount = db.scalar(select(func.coalesce(func.sum(Invoice.total), 0)).where(Invoice.status == InvoiceStatus.paid)) or 0

    return {
        "total_invoices": int(total_invoices),
        "pending_invoices": int(pending_invoices),
        "paid_invoices": int(paid_invoices),
        "pending_amount": float(pending_amount),
        "paid_amount": float(paid_amount),
    }


@router.get("/payments-by-method")
def payments_by_method(
    month: str = Query(..., description="Month in YYYY-MM format"), db: Session = Depends(get_db)
) -> dict:
    start, end = parse_month(month)
    rows = db.execute(
        select(Payment.method.label("method"), func.coalesce(func.sum(Payment.amount), 0).label("total_amount"))
        .where(Payment.date >= start, Payment.date < end)
        .group_by(Payment.method)
        .order_by(Payment.method.asc())
    ).all()

    return {
        "month": month,
        "items": [{"method": row.method.value, "total_amount": float(row.total_amount)} for row in rows],
    }
