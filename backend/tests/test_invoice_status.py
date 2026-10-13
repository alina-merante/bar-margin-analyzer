import datetime as dt
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    Payment,
    PaymentMethod,
)
from app.routers.finance import invoice_to_dict
from app.services.invoice_status import (
    get_invoice_payment_status,
)


def test_payment_status_requires_a_fully_recorded_payment():
    assert (
        get_invoice_payment_status(InvoiceStatus.paid, Decimal("50"), Decimal("50"))
        == InvoiceStatus.paid
    )
    assert (
        get_invoice_payment_status(InvoiceStatus.paid, Decimal("50"), Decimal("0"))
        == InvoiceStatus.pending
    )
    assert (
        get_invoice_payment_status(InvoiceStatus.pending, Decimal("50"), Decimal("50"))
        == InvoiceStatus.pending
    )


def test_invoice_api_status_changes_only_after_full_payment_is_linked():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        invoice = Invoice(
            supplier="Fornitore",
            invoice_number="FT-1",
            issue_date=dt.date(2026, 10, 1),
            due_date=dt.date(2026, 10, 13),
            total=Decimal("50.00"),
            vat=Decimal("0.00"),
            status=InvoiceStatus.paid,
        )
        session.add(invoice)
        session.commit()
        session.refresh(invoice)

        assert invoice_to_dict(invoice, session)["status"] == "pending"

        payment = Payment(
            date=dt.date(2026, 10, 13),
            amount=Decimal("50.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="Fornitore",
            reference="PAY-1",
        )
        session.add(payment)
        session.flush()
        session.add(InvoicePaymentLink(invoice_id=invoice.id, payment_id=payment.id))
        session.commit()

        assert invoice_to_dict(invoice, session)["status"] == "paid"

    engine.dispose()

