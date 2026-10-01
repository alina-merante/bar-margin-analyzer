import datetime as dt
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    Transaction,
)
from app.routers.analytics import expenses_by_category, invoices_summary, monthly_pnl
from app.routers.finance import (
    LinkPaymentPayload,
    PaymentCreate,
    ReconcileTransactionPayload,
    create_payment,
    delete_invoice,
    get_transaction_candidates,
    link_payment,
    list_invoices,
    reconcile_invoice_transaction,
)


@pytest.fixture

def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reconciliation.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_invoice(db, total="420.00", status=InvoiceStatus.pending):
    invoice = Invoice(
        supplier="TORREFAZIONE ITALIANA S.p.A.",
        invoice_number="TC-2026-071",
        issue_date=dt.date(2026, 7, 2),
        due_date=dt.date(2026, 7, 10),
        total=Decimal(total),
        vat=Decimal("60.00"),
        status=status,
    )
    db.add(invoice)
    db.commit()
    return invoice


def add_transaction(db, amount="-420.00", date=dt.date(2026, 7, 3), description=None):
    transaction = Transaction(
        date=date,
        description=description or "SEPA transfer - Torrefazione Italiana S.p.A.",
        amount=Decimal(amount),
        counterparty="Torrefazione Italiana S.p.A.",
    )
    db.add(transaction)
    db.commit()
    return transaction


def reconcile(db, invoice, transaction):
    return reconcile_invoice_transaction(
        invoice.id,
        ReconcileTransactionPayload(transaction_id=transaction.id),
        db,
    )


def test_exact_transaction_is_candidate_without_database_changes(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)

    result = get_transaction_candidates(invoice.id, db)

    assert result["linked_amount"] == 0.0
    assert result["remaining_amount"] == 420.0
    assert [item["id"] for item in result["candidates"]] == [transaction.id]
    assert result["candidates"][0]["amount"] == -420.0
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_candidate_search_excludes_positive_used_and_over_residual_transactions(db):
    invoice = add_invoice(db)
    positive = add_transaction(db, amount="100.00", description="Incoming transfer")
    over_residual = add_transaction(db, amount="-500.00", description="Supplier payment")
    used = add_transaction(db, amount="-100.00", description="Already used")
    payment = Payment(
        date=used.date,
        amount=Decimal("100.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=used.counterparty,
        reference=used.description,
        transaction_id=used.id,
    )
    db.add(payment)
    db.commit()

    candidates = get_transaction_candidates(invoice.id, db)["candidates"]

    assert [item["id"] for item in candidates] == []
    assert db.get(Transaction, positive.id) is not None
    assert db.get(Transaction, over_residual.id) is not None


def test_reconcile_full_payment_links_transaction_and_marks_invoice_paid(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)

    result = reconcile(db, invoice, transaction)

    payment = db.scalar(select(Payment))
    link = db.scalar(select(InvoicePaymentLink))
    assert payment.amount == Decimal("420.00")
    assert payment.transaction_id == transaction.id
    assert payment.date == transaction.date
    assert payment.method == PaymentMethod.bank_transfer
    assert link.invoice_id == invoice.id
    assert link.payment_id == payment.id
    assert result["invoice_status"] == "paid"
    assert result["linked_amount"] == 420.0
    assert result["remaining_amount"] == 0.0
    assert invoice.status == InvoiceStatus.paid


@pytest.mark.parametrize(
    ("description", "expected_method"),
    [
        ("SEPA transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Bank transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Bonifico - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Card payment - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Card - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Pagamento con carta - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Outgoing debit - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
    ],
)
def test_reconciliation_classifies_payment_method_from_transaction(
    db, description, expected_method
):
    invoice = add_invoice(db)
    transaction = add_transaction(db, description=description)

    reconcile(db, invoice, transaction)

    payment = db.scalar(select(Payment))
    assert payment.method == expected_method


def test_unlinked_invoice_can_be_deleted(db):
    invoice = add_invoice(db)

    result = delete_invoice(invoice.id, db)

    assert result == {"ok": True, "deleted_invoice_id": invoice.id}
    assert db.get(Invoice, invoice.id) is None
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


@pytest.mark.parametrize("payment_amount", ["420.00", "200.00"])
def test_invoice_with_reconciled_payment_cannot_be_deleted(db, payment_amount):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount=f"-{payment_amount}")
    reconcile(db, invoice, transaction)
    original_invoice_status = invoice.status
    original_transaction = (transaction.date, transaction.description, transaction.amount)
    payment = db.scalar(select(Payment))
    link = db.scalar(select(InvoicePaymentLink))

    with pytest.raises(HTTPException) as error:
        delete_invoice(invoice.id, db)

    assert error.value.status_code == 409
    assert error.value.detail == "La fattura non può essere eliminata perché contiene pagamenti riconciliati."
    db.expire_all()
    assert db.get(Invoice, invoice.id).status == original_invoice_status
    assert db.get(Payment, payment.id).transaction_id == transaction.id
    assert db.get(InvoicePaymentLink, link.id).invoice_id == invoice.id
    current_transaction = db.get(Transaction, transaction.id)
    assert (current_transaction.date, current_transaction.description, current_transaction.amount) == original_transaction


def test_reconcile_partial_payment_keeps_invoice_pending_and_exposes_residual(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-200.00")

    result = reconcile(db, invoice, transaction)
    invoice_response = list_invoices(status=None, supplier=None, month=None, db=db)[0]

    assert result["invoice_status"] == "pending"
    assert invoice_response["linked_amount"] == 200.0
    assert invoice_response["remaining_amount"] == 220.0
    assert invoice.status == InvoiceStatus.pending


def test_multiple_transactions_can_pay_one_invoice(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00")
    second = add_transaction(
        db,
        amount="-220.00",
        date=dt.date(2026, 7, 8),
        description="Second transfer - Torrefazione Italiana S.p.A.",
    )

    first_result = reconcile(db, invoice, first)
    second_result = reconcile(db, invoice, second)

    assert first_result["remaining_amount"] == 220.0
    assert second_result["invoice_status"] == "paid"
    assert db.query(Payment).count() == 2
    assert db.query(InvoicePaymentLink).count() == 2


def test_expenses_by_category_matches_completed_invoice_pnl_costs(db):
    coffee_invoice = add_invoice(db, total="420.00")
    coffee_invoice.supplier = "Torrefazione Italiana S.p.A."
    coffee_invoice.invoice_number = "TC-2026-071"
    reconcile(db, coffee_invoice, add_transaction(db, amount="-420.00"))

    beverage_invoice = add_invoice(db, total="500.00")
    beverage_invoice.supplier = "DISTRIBUZIONE BEVANDE S.R.L."
    beverage_invoice.invoice_number = "DB-2026-072"
    reconcile(
        db,
        beverage_invoice,
        add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 15)),
    )
    reconcile(
        db,
        beverage_invoice,
        add_transaction(db, amount="-300.00", date=dt.date(2026, 7, 18)),
    )

    partial_invoice = add_invoice(db, total="100.00")
    partial_invoice.supplier = "Servizi Alfa"
    partial_invoice.invoice_number = "SA-2026-001"
    reconcile(db, partial_invoice, add_transaction(db, amount="-40.00"))

    add_transaction(db, amount="-90.00", description="Unlinked bank debit")

    result = expenses_by_category("2026-07", db)
    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert result["items"] == [
        {"category": "Bevande", "total_amount": 500.0},
        {"category": "Caffe", "total_amount": 420.0},
    ]
    assert sum(item["total_amount"] for item in result["items"]) == float(pnl["expenses"]) == 920.0
    assert expenses_by_category("2026-08", db)["items"] == []


def test_positive_transaction_cannot_pay_invoice(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="100.00", description="Incoming transfer")

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 400
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_overpayment_is_rejected(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-421.00")

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 409
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_same_transaction_cannot_be_reconciled_twice(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    reconcile(db, invoice, transaction)

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 409
    assert db.query(Payment).count() == 1
    assert db.query(InvoicePaymentLink).count() == 1


def test_database_rejects_two_payments_for_same_transaction(db):
    transaction = add_transaction(db)
    first_payment = Payment(
        date=transaction.date,
        amount=Decimal("200.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=transaction.counterparty,
        reference="first",
        transaction_id=transaction.id,
    )
    second_payment = Payment(
        date=transaction.date,
        amount=Decimal("220.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=transaction.counterparty,
        reference="second",
        transaction_id=transaction.id,
    )
    db.add_all([first_payment, second_payment])

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()
    assert db.scalars(select(Payment)).all() == []


def test_same_payment_cannot_be_linked_to_two_invoices(db):
    first_invoice = add_invoice(db)
    second_invoice = add_invoice(db, total="500.00")
    payment = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("200.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="manual payment",
        ),
        db,
    )

    link_payment(first_invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)
    with pytest.raises(HTTPException) as error:
        link_payment(second_invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)

    assert error.value.status_code == 409
    assert db.query(InvoicePaymentLink).count() == 1


def test_legacy_link_endpoint_rejects_overpayment(db):
    invoice = add_invoice(db)
    payment = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("421.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="overpayment",
        ),
        db,
    )

    with pytest.raises(HTTPException) as error:
        link_payment(invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)

    assert error.value.status_code == 409
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_reconciliation_rolls_back_payment_if_link_creation_fails(db, monkeypatch):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    original_add = db.add

    def fail_on_link(instance):
        if isinstance(instance, InvoicePaymentLink):
            raise RuntimeError("simulated link failure")
        original_add(instance)

    monkeypatch.setattr(db, "add", fail_on_link)

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 500
    monkeypatch.setattr(db, "add", original_add)
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_transaction_delete_is_restricted_after_reconciliation(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    reconcile(db, invoice, transaction)

    db.delete(transaction)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert db.get(Transaction, transaction.id) is not None
    assert db.query(Payment).count() == 1


def test_manual_payment_keeps_transaction_id_null(db):
    result = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("25.00"),
            method=PaymentMethod.cash,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="cash",
        ),
        db,
    )

    assert db.get(Payment, result["id"]).transaction_id is None


def test_invoice_summary_counts_only_remaining_amount_after_partial_payment(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-200.00")
    reconcile(db, invoice, transaction)

    summary = invoices_summary(db)

    assert summary["pending_amount"] == 220.0
    assert summary["pending_invoices"] == 1


@pytest.mark.parametrize(
    ("payment_amount", "expected_pending_amount", "expected_pending_invoices", "expected_expenses"),
    [
        (None, 500.0, 1, Decimal("0.00")),
        ("-200.00", 300.0, 1, Decimal("0.00")),
        ("-500.00", 0.0, 0, Decimal("500.00")),
    ],
)
def test_invoice_summary_and_pnl_follow_partial_payment_residual(
    db, payment_amount, expected_pending_amount, expected_pending_invoices, expected_expenses
):
    invoice = add_invoice(db, total="500.00")
    if payment_amount is not None:
        transaction = add_transaction(db, amount=payment_amount)
        reconcile(db, invoice, transaction)

    summary = invoices_summary(db)
    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert summary["pending_amount"] == expected_pending_amount
    assert summary["pending_invoices"] == expected_pending_invoices
    assert pnl["expenses"] == expected_expenses


def test_pnl_counts_invoice_once_in_month_partial_and_final_payment_happen(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 3))
    second = add_transaction(db, amount="-220.00", date=dt.date(2026, 7, 20))
    reconcile(db, invoice, first)
    reconcile(db, invoice, second)

    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert pnl["expenses"] == Decimal("420.00")


def test_pnl_counts_invoice_only_in_month_final_payment_completes_balance(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 3))
    second = add_transaction(db, amount="-220.00", date=dt.date(2026, 8, 2))
    reconcile(db, invoice, first)
    reconcile(db, invoice, second)

    july = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))
    august = monthly_pnl(db, dt.date(2026, 8, 1), dt.date(2026, 9, 1))

    assert july["expenses"] == Decimal("0.00")
    assert august["expenses"] == Decimal("420.00")
