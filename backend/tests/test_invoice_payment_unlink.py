import datetime as dt
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Invoice, InvoicePaymentLink, InvoiceStatus, Payment, PaymentMethod, Transaction
from app.routers.analytics import overview
from finance_test_support import finance_request, finance_response


@pytest.fixture
def db(finance_http_env):
    with finance_http_env["sessionmaker"]() as session:
        session.info.update(
            finance_client=finance_http_env["client"],
            csrf_token=finance_http_env["csrf_token"],
            bar_id=finance_http_env["bar_id"],
        )
        yield session


def add_invoice(db, total="120.00", number="12"):
    invoice = Invoice(
        bar_id=db.info["bar_id"],
        supplier="aaaaa",
        invoice_number=number,
        issue_date=dt.date(2026, 7, 2),
        due_date=dt.date(2026, 7, 20),
        total=Decimal(total),
        vat=Decimal("0.00"),
        status=InvoiceStatus.pending,
    )
    db.add(invoice)
    db.commit()
    return invoice


def add_transaction(db, amount="-120.00", day=12):
    transaction = Transaction(
        bar_id=db.info["bar_id"],
        date=dt.date(2026, 7, day),
        description="Pagamento carta Pulizie Splendore",
        amount=Decimal(amount),
        counterparty="Pulizie Splendore",
    )
    db.add(transaction)
    db.commit()
    return transaction


def reconcile(db, invoice, transaction):
    finance_response(
        finance_request(
            db,
            "POST",
            f"/invoices/{invoice.id}/reconcile-transaction",
            payload={"transaction_id": transaction.id},
        )
    )
    return db.scalar(select(Payment).where(Payment.transaction_id == transaction.id))


def link_of(db, payment):
    return db.scalar(select(InvoicePaymentLink).where(InvoicePaymentLink.payment_id == payment.id))


def add_manual(db, invoice, amount="50.00"):
    payment = Payment(
        bar_id=db.info["bar_id"],
        date=dt.date(2026, 7, 5),
        amount=Decimal(amount),
        method=PaymentMethod.cash,
        counterparty="aaaaa",
        reference="contanti",
    )
    db.add(payment)
    db.flush()
    link = InvoicePaymentLink(
        bar_id=db.info["bar_id"],
        invoice_id=invoice.id,
        payment_id=payment.id,
    )
    db.add(link)
    db.commit()
    return payment, link


def invoice_row(db, invoice):
    return next(r for r in list_invoices(status=None, supplier=None, month=None, db=db) if r["id"] == invoice.id)


def get_transaction_candidates(invoice_id, db):
    return finance_response(
        finance_request(db, "GET", f"/invoices/{invoice_id}/transaction-candidates")
    )


def list_invoice_payments(invoice_id, db):
    return finance_response(
        finance_request(db, "GET", f"/invoices/{invoice_id}/payments")
    )


def list_invoices(*, status=None, supplier=None, month=None, db):
    params = {
        key: value
        for key, value in {"status": status, "supplier": supplier, "month": month}.items()
        if value is not None
    }
    return finance_response(finance_request(db, "GET", "/invoices", params=params))


def unlink_invoice_payment(invoice_id, link_id, db):
    return finance_response(
        finance_request(
            db,
            "DELETE",
            f"/invoices/{invoice_id}/payments/{link_id}",
        )
    )


def test_unlink_bank_payment_from_paid_invoice_keeps_transaction_and_frees_it(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    payment = reconcile(db, invoice, transaction)
    payment_id = payment.id
    link = link_of(db, payment)
    assert invoice.status == InvoiceStatus.paid

    result = unlink_invoice_payment(invoice.id, link.id, db)

    assert result["payment_deleted"] is True
    assert result["invoice_status"] == "pending"
    assert result["linked_amount"] == 0.0
    assert result["remaining_amount"] == 120.0
    db.expire_all()
    assert db.get(Invoice, invoice.id).status == InvoiceStatus.pending
    assert db.get(Payment, payment_id) is None
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    kept = db.get(Transaction, transaction.id)
    assert kept is not None and kept.amount == Decimal("-120.00")
    candidates = get_transaction_candidates(invoice.id, db)["candidates"]
    assert [c["id"] for c in candidates] == [transaction.id]

    again = reconcile(db, invoice, transaction)
    assert again is not None
    assert db.get(Invoice, invoice.id).status == InvoiceStatus.paid


def test_unlink_manual_payment_keeps_payment_record(db):
    invoice = add_invoice(db)
    payment, link = add_manual(db, invoice, "50.00")

    result = unlink_invoice_payment(invoice.id, link.id, db)

    assert result["payment_deleted"] is False
    assert result["transaction_id"] is None
    assert result["linked_amount"] == 0.0
    assert result["remaining_amount"] == 120.0
    db.expire_all()
    assert db.get(Payment, payment.id) is not None
    assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_unlink_one_of_multiple_partial_payments_recalculates_status(db):
    invoice = add_invoice(db, total="120.00")
    tx = add_transaction(db, amount="-70.00")
    bank_payment = reconcile(db, invoice, tx)
    manual, _ = add_manual(db, invoice, "50.00")
    invoice.status = InvoiceStatus.paid
    db.commit()

    result = unlink_invoice_payment(invoice.id, link_of(db, bank_payment).id, db)

    assert result["invoice_status"] == "pending"
    assert result["linked_amount"] == 50.0
    assert result["remaining_amount"] == 70.0
    remaining = list_invoice_payments(invoice.id, db)["payments"]
    assert [p["payment_id"] for p in remaining] == [manual.id]


def test_unlink_from_partially_paid_invoice_stays_pending(db):
    invoice = add_invoice(db)
    _, link1 = add_manual(db, invoice, "30.00")
    add_manual(db, invoice, "40.00")

    result = unlink_invoice_payment(invoice.id, link1.id, db)

    assert result["invoice_status"] == "pending"
    assert result["linked_amount"] == 40.0
    assert result["remaining_amount"] == 80.0


def test_unlink_missing_invoice_returns_404(db):
    with pytest.raises(HTTPException) as exc:
        unlink_invoice_payment(999, 1, db)
    assert exc.value.status_code == 404


def test_unlink_missing_or_foreign_link_returns_404_without_changes(db):
    invoice = add_invoice(db)
    other = add_invoice(db, number="13")
    transaction = add_transaction(db)
    payment = reconcile(db, other, transaction)
    link = link_of(db, payment)

    for link_id in (9999, link.id):
        with pytest.raises(HTTPException) as exc:
            unlink_invoice_payment(invoice.id, link_id, db)
        assert exc.value.status_code == 404

    db.expire_all()
    assert db.get(Payment, payment.id) is not None
    assert link_of(db, payment) is not None
    assert db.get(Invoice, other.id).status == InvoiceStatus.paid
    assert db.get(Transaction, transaction.id) is not None


def test_second_unlink_of_same_link_returns_404(db):
    invoice = add_invoice(db)
    payment = reconcile(db, invoice, add_transaction(db))
    link_id = link_of(db, payment).id

    unlink_invoice_payment(invoice.id, link_id, db)
    with pytest.raises(HTTPException) as exc:
        unlink_invoice_payment(invoice.id, link_id, db)

    assert exc.value.status_code == 404
    assert db.scalars(select(Transaction)).all() != []


def test_failure_rolls_back_all_changes(db, monkeypatch):
    invoice = add_invoice(db)
    payment = reconcile(db, invoice, add_transaction(db))
    link_id = link_of(db, payment).id

    def boom(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.finance.invoice_linked_amount", boom)
    with pytest.raises(HTTPException) as exc:
        unlink_invoice_payment(invoice.id, link_id, db)
    monkeypatch.undo()

    assert exc.value.status_code == 500
    db.expire_all()
    assert db.get(Invoice, invoice.id).status == InvoiceStatus.paid
    assert db.get(Payment, payment.id) is not None
    assert db.get(InvoicePaymentLink, link_id) is not None


def test_dashboard_reflects_unlink(db):
    invoice = add_invoice(db)
    payment = reconcile(db, invoice, add_transaction(db))

    assert invoice_row(db, invoice)["status"] == "paid"
    assert overview(month="2026-07", db=db)["pnl_summary"]["expenses"] == 120.0

    unlink_invoice_payment(invoice.id, link_of(db, payment).id, db)

    row = invoice_row(db, invoice)
    assert row["status"] == "pending"
    assert row["linked_amount"] == 0.0
    assert row["remaining_amount"] == 120.0
    assert overview(month="2026-07", db=db)["pnl_summary"]["expenses"] == 0.0
