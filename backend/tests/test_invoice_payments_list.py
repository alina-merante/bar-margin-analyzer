import datetime as dt
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Invoice, InvoicePaymentLink, InvoiceStatus, Payment, PaymentMethod, Transaction
from app.routers.finance import list_invoice_payments


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'payments.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_invoice(db, total="400.00", status=InvoiceStatus.pending):
    invoice = Invoice(
        supplier="Fornitore",
        invoice_number="F-1",
        issue_date=dt.date(2026, 7, 2),
        due_date=dt.date(2026, 7, 10),
        total=Decimal(total),
        vat=Decimal("0.00"),
        status=status,
    )
    db.add(invoice)
    db.commit()
    return invoice


def add_payment(db, invoice, amount, date, method=PaymentMethod.cash, transaction=None, reference="rif"):
    payment = Payment(
        date=date,
        amount=Decimal(amount),
        method=method,
        counterparty="Fornitore",
        reference=reference,
        transaction_id=transaction.id if transaction else None,
    )
    db.add(payment)
    db.flush()
    db.add(InvoicePaymentLink(invoice_id=invoice.id, payment_id=payment.id))
    db.commit()
    return payment


def test_paid_invoice_with_single_payment(db):
    invoice = add_invoice(db, status=InvoiceStatus.paid)
    payment = add_payment(db, invoice, "400.00", dt.date(2026, 7, 5))

    result = list_invoice_payments(invoice.id, db)

    assert result["linked_amount"] == 400.0
    assert result["remaining_amount"] == 0.0
    assert len(result["payments"]) == 1
    assert result["payments"][0]["payment_id"] == payment.id
    assert result["payments"][0]["link_id"] is not None
    assert result["payments"][0]["amount"] == 400.0
    assert result["payments"][0]["reference"] == "rif"
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.paid


def test_invoice_with_multiple_partial_payments_ordered_by_date(db):
    invoice = add_invoice(db)
    add_payment(db, invoice, "100.00", dt.date(2026, 7, 9))
    add_payment(db, invoice, "150.00", dt.date(2026, 7, 3))

    result = list_invoice_payments(invoice.id, db)

    assert [p["amount"] for p in result["payments"]] == [150.0, 100.0]
    assert result["linked_amount"] == 250.0
    assert result["remaining_amount"] == 150.0
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.pending


def test_invoice_without_payments(db):
    invoice = add_invoice(db)

    result = list_invoice_payments(invoice.id, db)

    assert result["payments"] == []
    assert result["linked_amount"] == 0.0
    assert result["remaining_amount"] == 400.0


def test_missing_invoice_returns_404(db):
    with pytest.raises(HTTPException) as exc:
        list_invoice_payments(999, db)

    assert exc.value.status_code == 404


def test_bank_and_manual_payments_are_distinguished(db):
    invoice = add_invoice(db)
    transaction = Transaction(
        date=dt.date(2026, 7, 4),
        description="SEPA",
        amount=Decimal("-100.00"),
        counterparty="Fornitore",
    )
    db.add(transaction)
    db.commit()
    add_payment(db, invoice, "100.00", dt.date(2026, 7, 4), PaymentMethod.bank_transfer, transaction)
    add_payment(db, invoice, "50.00", dt.date(2026, 7, 6), PaymentMethod.cash)

    bank, manual = list_invoice_payments(invoice.id, db)["payments"]

    assert bank["source"] == "bank"
    assert bank["transaction_id"] == transaction.id
    assert bank["method"] == "bank_transfer"
    assert manual["source"] == "manual"
    assert manual["transaction_id"] is None
    assert manual["method"] == "cash"
