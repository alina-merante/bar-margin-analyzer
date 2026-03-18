import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, InvoicePaymentLink, InvoiceStatus, Payment, PaymentMethod

router = APIRouter(tags=["invoices", "payments"])


class InvoiceCreate(BaseModel):
    supplier: str
    invoice_number: str
    issue_date: dt.date
    due_date: dt.date
    total: Decimal
    vat: Decimal
    status: InvoiceStatus = InvoiceStatus.pending


class PaymentCreate(BaseModel):
    date: dt.date
    amount: Decimal
    method: PaymentMethod
    counterparty: str
    reference: str


class LinkPaymentPayload(BaseModel):
    payment_id: int


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


@router.post("/invoices")
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)) -> dict:
    invoice = Invoice(
        supplier=payload.supplier.strip(),
        invoice_number=payload.invoice_number.strip(),
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        total=payload.total,
        vat=payload.vat,
        status=payload.status,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return {
        "id": invoice.id,
        "supplier": invoice.supplier,
        "invoice_number": invoice.invoice_number,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "total": float(invoice.total),
        "vat": float(invoice.vat),
        "status": invoice.status.value,
    }


@router.get("/invoices")
def list_invoices(
    status: InvoiceStatus | None = Query(default=None),
    supplier: str | None = Query(default=None),
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Invoice)

    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    if supplier:
        stmt = stmt.where(Invoice.supplier.ilike(f"%{supplier.strip()}%"))
    if month:
        start, end = parse_month(month)
        stmt = stmt.where(Invoice.issue_date >= start, Invoice.issue_date < end)

    invoices = db.scalars(stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc())).all()
    return [
        {
            "id": row.id,
            "supplier": row.supplier,
            "invoice_number": row.invoice_number,
            "issue_date": row.issue_date.isoformat(),
            "due_date": row.due_date.isoformat(),
            "total": float(row.total),
            "vat": float(row.vat),
            "status": row.status.value,
        }
        for row in invoices
    ]


@router.post("/payments")
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db)) -> dict:
    payment = Payment(
        date=payload.date,
        amount=payload.amount,
        method=payload.method,
        counterparty=payload.counterparty.strip(),
        reference=payload.reference.strip(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {
        "id": payment.id,
        "date": payment.date.isoformat(),
        "amount": float(payment.amount),
        "method": payment.method.value,
        "counterparty": payment.counterparty,
        "reference": payment.reference,
    }


@router.get("/payments")
def list_payments(
    method: PaymentMethod | None = Query(default=None),
    counterparty: str | None = Query(default=None),
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Payment)

    if method is not None:
        stmt = stmt.where(Payment.method == method)
    if counterparty:
        stmt = stmt.where(Payment.counterparty.ilike(f"%{counterparty.strip()}%"))
    if month:
        start, end = parse_month(month)
        stmt = stmt.where(Payment.date >= start, Payment.date < end)

    payments = db.scalars(stmt.order_by(Payment.date.desc(), Payment.id.desc())).all()
    return [
        {
            "id": row.id,
            "date": row.date.isoformat(),
            "amount": float(row.amount),
            "method": row.method.value,
            "counterparty": row.counterparty,
            "reference": row.reference,
        }
        for row in payments
    ]


@router.post("/invoices/{invoice_id}/link-payment")
def link_payment(invoice_id: int, payload: LinkPaymentPayload, db: Session = Depends(get_db)) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="invoice not found")

    payment = db.get(Payment, payload.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment not found")

    existing_link = db.scalar(
        select(InvoicePaymentLink).where(
            InvoicePaymentLink.invoice_id == invoice_id,
            InvoicePaymentLink.payment_id == payload.payment_id,
        )
    )
    if existing_link:
        raise HTTPException(status_code=400, detail="payment already linked to invoice")

    link = InvoicePaymentLink(invoice_id=invoice.id, payment_id=payment.id)
    db.add(link)

    linked_total_result = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(InvoicePaymentLink, InvoicePaymentLink.payment_id == Payment.id)
        .where(InvoicePaymentLink.invoice_id == invoice.id)
    )
    linked_total = Decimal(linked_total_result.scalar_one()) + Decimal(payment.amount)

    invoice.status = InvoiceStatus.paid if linked_total >= Decimal(invoice.total) else InvoiceStatus.pending

    db.commit()
    db.refresh(invoice)
    db.refresh(link)

    return {
        "id": link.id,
        "invoice_id": link.invoice_id,
        "payment_id": link.payment_id,
        "invoice_status": invoice.status.value,
        "linked_total": float(linked_total),
        "invoice_total": float(invoice.total),
    }
