import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import (
    DailyCashClosure,
    ExpenseCategory,
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    Transaction,
)
from app.routers.analytics import monthly_pnl


def build_session():
    engine = create_engine("sqlite:///./test_analytics.db")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def add_cash_closure(session, total_amount):
    session.add(DailyCashClosure(date=date(2026, 9, 1), total_amount=total_amount))


def add_bank_transaction(session, amount, counterparty):
    session.add(
        Transaction(
            date=date(2026, 9, 2),
            description="bank movement",
            amount=amount,
            counterparty=counterparty,
            category_id=None,
        )
    )


def add_invoice(session, total, vat, status, supplier="Supplier A", invoice_number="INV-1"):
    invoice = Invoice(
        supplier=supplier,
        invoice_number=invoice_number,
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 9, 15),
        total=total,
        vat=vat,
        status=status,
    )
    session.add(invoice)
    session.flush()
    return invoice


def add_payment(session, amount, counterparty="Supplier A", reference="PAY-1"):
    payment = Payment(
        date=date(2026, 9, 10),
        amount=amount,
        method=PaymentMethod.bank_transfer,
        counterparty=counterparty,
        reference=reference,
    )
    session.add(payment)
    session.flush()
    return payment


def link_payment(session, invoice, payment):
    session.add(InvoicePaymentLink(invoice_id=invoice.id, payment_id=payment.id))


def test_monthly_pnl_counts_only_paid_reconciled_invoices_once():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        add_bank_transaction(session, Decimal("-120.00"), "Supplier A")
        add_bank_transaction(session, Decimal("50.00"), "Customer")

        invoice = add_invoice(session, Decimal("120.00"), Decimal("20.00"), InvoiceStatus.pending)
        payment = add_payment(session, Decimal("150.00"))
        link_payment(session, invoice, payment)
        invoice.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["revenue"] == Decimal("1000.00")
        assert result["expenses"] == Decimal("260.00")
        assert result["profit"] == Decimal("740.00")


def test_unpaid_invoice_does_not_create_cost():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("120.00"), Decimal("20.00"), InvoiceStatus.pending)
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("0.00")


def test_payment_without_invoice_does_not_create_cost():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        add_bank_transaction(session, Decimal("-120.00"), "Supplier A")
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("120.00")


def test_negative_bank_transactions_are_counted_as_expenses():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        add_bank_transaction(session, Decimal("-120.00"), "Supplier A")
        add_bank_transaction(session, Decimal("50.00"), "Customer")
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("120.00")
        assert result["profit"] == Decimal("880.00")


def test_paid_invoice_without_link_has_no_cost():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("120.00"), Decimal("20.00"), InvoiceStatus.paid)
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("0.00")


def test_linked_payment_on_pending_invoice_has_no_cost():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("120.00"), Decimal("20.00"), InvoiceStatus.pending)
        payment = add_payment(session, Decimal("150.00"))
        link_payment(session, invoice, payment)
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("0.00")


def test_multiple_payments_on_same_invoice_count_once():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending)
        payment_one = add_payment(session, Decimal("40.00"), reference="PAY-1")
        payment_two = add_payment(session, Decimal("60.00"), reference="PAY-2")
        link_payment(session, invoice, payment_one)
        link_payment(session, invoice, payment_two)
        invoice.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("100.00")


def test_single_payment_for_two_invoices_counts_total_once_per_invoice():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice_one = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-1")
        invoice_two = add_invoice(session, Decimal("200.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-2")
        payment = add_payment(session, Decimal("300.00"), reference="PAY-1")
        link_payment(session, invoice_one, payment)
        link_payment(session, invoice_two, payment)
        invoice_one.status = InvoiceStatus.paid
        invoice_two.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("300.00")


def test_partial_payment_keeps_invoice_unpaid_and_cost_zero():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending)
        payment = add_payment(session, Decimal("40.00"))
        link_payment(session, invoice, payment)
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("0.00")


def test_payment_greater_than_invoice_keeps_cost_at_invoice_total():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending)
        payment = add_payment(session, Decimal("120.00"))
        link_payment(session, invoice, payment)
        invoice.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("100.00")


def test_multiple_paid_invoices_sum_to_total_expenses():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice_one = add_invoice(session, Decimal("120.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-1")
        invoice_two = add_invoice(session, Decimal("350.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-2")
        invoice_three = add_invoice(session, Decimal("80.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-3")
        payment_one = add_payment(session, Decimal("120.00"), reference="PAY-1")
        payment_two = add_payment(session, Decimal("350.00"), reference="PAY-2")
        payment_three = add_payment(session, Decimal("80.00"), reference="PAY-3")
        link_payment(session, invoice_one, payment_one)
        link_payment(session, invoice_two, payment_two)
        link_payment(session, invoice_three, payment_three)
        invoice_one.status = InvoiceStatus.paid
        invoice_two.status = InvoiceStatus.paid
        invoice_three.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("550.00")


def test_invoice_paid_in_following_month_is_counted_in_payment_month():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending)
        payment = add_payment(session, Decimal("100.00"), reference="PAY-1")
        link_payment(session, invoice, payment)
        invoice.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("100.00")


def test_duplicate_invoice_is_not_double_counted():
    with build_session() as session:
        add_cash_closure(session, Decimal("1000.00"))
        invoice_one = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-1")
        invoice_two = add_invoice(session, Decimal("100.00"), Decimal("0.00"), InvoiceStatus.pending, invoice_number="INV-1")
        payment = add_payment(session, Decimal("100.00"), reference="PAY-1")
        link_payment(session, invoice_one, payment)
        link_payment(session, invoice_two, payment)
        invoice_one.status = InvoiceStatus.paid
        invoice_two.status = InvoiceStatus.paid
        session.commit()

        result = monthly_pnl(session, date(2026, 9, 1), date(2026, 10, 1))

        assert result["expenses"] == Decimal("100.00")
